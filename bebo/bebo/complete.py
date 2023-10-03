#  Copyright (c) 2019-2023 SRI International.

import argparse
import dns.asyncquery
import dns.asyncresolver
import functools
import logging
import os
import quart
import quart_trio
import random
import socket
import struct
import sys
import time
import trio
import trio.socket

import bebo.decode
import bebo.lruqueue
import bebo.protocol
import bebo.storage
import bebo.util


BEBO_PORT = 0xbeb0
MAX_GET_COUNT = 100
RESOLUTION_INTERVAL = 60
STARTUP_RESOLUTION_INTERVAL = 10
STARTUP_INTERVAL = 120


async def read_exactly(stream, count):
    s = b''
    while count > 0:
        n = await stream.receive_some(count)
        if n == b'':
            raise EOFError
        count = count - len(n)
        s = s + n
    return s


class Neighbor:
    def __init__(self, name):
        self.name = name
        self.addresses = set()
        self.send_queue = bebo.lruqueue.LRUQueue()
        self.cancel_scopes = []

    def disconnect(self):
        scopes = self.cancel_scopes
        self.cancel_scopes = []
        if scopes:
            for scope in scopes:
                scope.cancel()

    def __str__(self):
        return f'neighbor {self.name}'


class Server:
    def __init__(self, db: bebo.storage.Storage):
        self.db = db
        self.neighbors = {}
        self.neighbor_names = []
        self.connected_neighbors = 0
        # The blocking limit on the channel has to be less than the number of
        # initial neighbors or we can deadlock at startup
        self.me = set()
        self.version = None

    def is_me(self, address):
        return address in self.me

    async def read_loop(self, neighbor, stream):
        log = logging.getLogger('bebo.read')
        while True:
            data = await read_exactly(stream, 4)
            (l,) = struct.unpack('!I', data)
            data = await read_exactly(stream, l)
            if data:
                message = bebo.protocol.from_cbor(data)
                log.debug('%s received %s', neighbor, message.key())
                if isinstance(message, bebo.protocol.RelayMessage):
                    await self.inject(message, neighbor)
                else:
                    logging.error('%s unhandled message: %s', neighbor, message)
            else:
                logging.debug('%s EOF', neighbor)
                break

    async def send_loop(self, neighbor, stream):
        # log = logging.getLogger('bebo.send')
        while True:
            message = await neighbor.send_queue.read()
            data = message.to_cbor()
            l = len(data)
            packet = struct.pack("!I", l) + data
            try:
                await stream.send_all(packet)
            except Exception:
                # Try to put the message back!
                await neighbor.send_queue.unread(message)

    async def interact(self, neighbor, stream):
        async with trio.open_nursery() as nursery:
            nursery.start_soon(self.read_loop, neighbor, stream)
            nursery.start_soon(self.send_loop, neighbor, stream)

    async def reader(self, stream):
        log = logging.getLogger('bebo.incoming')
        peer = stream.socket.getpeername()
        # This isn't super efficient, but it's ok for now!
        found = False
        for neighbor in self.neighbors.values():
            if peer[0] in neighbor.addresses:
                found = True
                break
        if not found:
            log.error('rejecting connection from unknown address: %s', peer)
        # XXX check connection order
        stream.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

        with trio.CancelScope() as scope:
            neighbor.cancel_scopes.append(scope)
            log.info('%s connected from %s:%d', neighbor, peer[0], peer[1])
            try:
                async with stream:
                    await self.interact(neighbor, stream)
            except EOFError:
                # we can just log disconnected for this
                pass
            except Exception as e:
                log.error('%s caught exception %s', neighbor, repr(e))
            log.info('%s disconnected from %s:%d', neighbor, peer[0], peer[1])

    async def connector(self, neighbor):
        log = logging.getLogger('bebo.connector')
        with trio.CancelScope() as scope:
            neighbor.cancel_scopes.append(scope)
            log.debug('%s starting', neighbor)
            retry = True
            backoff = 1
            connected = False
            while retry:
                try:
                    log.debug('%s connecting', neighbor)
                    # We don't just use open_tcp_stream because we want to
                    # bind() our local address.  (We're using loopback
                    # aliases interfaces in testing, and we don't want the
                    # connection coming from some random source address
                    # (typically the "wrong" one) but from our published
                    # address.
                    address = random.choice(list(neighbor.addresses))
                    af = bebo.util.af_for_text_address(address)
                    if af == socket.AF_INET:
                        lsa = (self.address, 0)
                        psa = (address, self.port)
                    else:
                        lsa = (self.address, 0, 0, 0)
                        psa = (address, self.port, 0, 0)
                    s = trio.socket.socket(af)
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    await s.bind(lsa)
                    await s.connect(psa)
                    stream = trio.SocketStream(s)
                    peer = stream.socket.getpeername()
                    backoff = 1
                    connected = True
                    self.connected_neighbors += 1
                    log.info('%s connected at %s:%d', neighbor, peer[0],
                             peer[1])
                    async with stream:
                        await self.interact(neighbor, stream)
                except ConnectionError as e:
                    log.debug('%s caught connection exception %s', neighbor, e)
                except Exception as e:
                    log.error('%s caught exception %s', neighbor, repr(e))
                finally:
                    # We do this here so the count is right even if we
                    # get canceled.
                    if connected:
                        self.connected_neighbors -= 1
                if connected:
                    connected = False
                    log.info('%s disconnected from %s:%d', neighbor, peer[0],
                             peer[1])
                else:
                    log.debug('%s connection failed, backoff = %d', neighbor,
                              backoff)
                await trio.sleep(backoff)
                backoff = min(2 * backoff, 32)
            log.debug('%s finished', neighbor)

    async def periodic_purger(self):
        while True:
            await trio.sleep(10)
            self.db.purge()

    async def inject(self, message: bebo.protocol.Message,
                     originator=None):
        #
        # Inject a message into the network.  Returns a (seqno, created)
        # tuple.  Created is true iff. the message was not in storage
        # already when injected.
        #
        log = logging.getLogger('bebo.inject')
        seqno = 0
        existing = None
        want_broadcast = originator is None
        if isinstance(message, bebo.protocol.RelayMessage):
            # Add (or retrieve) the message from the database
            (existing, seqno) = self.db.add(message)
            if existing:
                want_broadcast = False
        log.debug('inject %s... broadcast = %s', message.key()[:16],
                  want_broadcast)
        if want_broadcast:
            # we can block sending and someone could change neighbors,
            # breaking our iterator, so make a copy of the current
            # neighbors
            copied = [x for x in self.neighbors.values()]
            for neighbor in copied:
                await neighbor.send_queue.write(message)
        return (seqno, existing is None)

    async def resolver(self, nursery):
        log = logging.getLogger('bebo.resolver')
        # maybe work around dnspython bug!
        res = dns.asyncresolver.get_default_resolver()
        res.ndots = None
        start_time = time.time()
        while True:
            log.debug('resolver awake')
            for name in self.neighbor_names:
                if name == self.name:
                    continue
                maybe_start = False
                neighbor = self.neighbors.get(name)
                if neighbor is None:
                    log.info('%s: adding new neighbor', name)
                    neighbor = Neighbor(name)
                    self.neighbors[name] = neighbor
                    maybe_start = True
                addresses = set()
                for rdtype in ['A', 'AAAA']:
                    try:
                        answer = await res.resolve(name, rdtype, search=True)
                        for rr in answer:
                            addresses.add(rr.address)
                    except Exception as e:
                        log.debug('%s %s resolution raised %s', name, rdtype,
                                  e)
                log.debug('%s: old = %s', name, neighbor.addresses)
                log.debug('%s: new = %s', name, addresses)
                no_overlap = addresses.intersection(neighbor.addresses) == set()
                neighbor.addresses = addresses
                if no_overlap:
                    log.info('%s: new addresses: %s', name, addresses)
                    neighbor.disconnect()
                    maybe_start = True
                if maybe_start and len(neighbor.addresses) > 0 and \
                   self.name < neighbor.name:
                    log.info('%s: starting', name)
                    nursery.start_soon(self.connector, neighbor)
            #
            # We wake up more frequently for a time afte we've just
            # started as it may be the whole cluster has just started
            # too and we'd like things to get going quickly.
            #
            if time.time() - start_time >= STARTUP_INTERVAL:
                sleep_time = RESOLUTION_INTERVAL
            else:
                sleep_time = STARTUP_RESOLUTION_INTERVAL
            log.debug('resolver asleep')
            await trio.sleep(sleep_time)

    async def main(self, argv):
        parser = argparse.ArgumentParser(description='bebo server')
        parser.add_argument('--address', '-a', metavar='ADDRESS',
                            default='0.0.0.0',
                            help='the address to listen on')
        parser.add_argument('--hostname', '-n', metavar='NAME',
                            default='',
                            help='the name of this host')
        parser.add_argument('--port', '-p', metavar='PORT', type=int,
                            default=BEBO_PORT,
                            help='the address to listen on')
        parser.add_argument('--http-port', '-P', metavar='PORT', type=int,
                            default=bebo.util.HTTP_PORT,
                            help='the address to listen on')
        parser.add_argument('neighbors', metavar='SERVER', nargs='*',
                            help='a bebo neighbor')
        parser.add_argument('--debug', '-d', action='store_true')
        parser.add_argument('--hex-mode', '-H', action='store_true')
        parser.add_argument('--logfile', '-L', metavar='FILENAME', default='',
                            help='log file name; uses stdout otherwise')
        args = parser.parse_args(argv)
        self.name = os.getenv('BEBO_HOSTNAME', args.hostname)
        if self.name is None:
            self.name = socket.getfqdn()
        self.debug = bebo.util.get_boolean_env('DEBUG', args.debug)
        self.address = os.getenv('ADDRESS', args.address)
        self.port = bebo.util.get_int_env('PORT', args.port)
        self.http_port = bebo.util.get_int_env('HTTP_PORT', args.http_port)
        self.address = bebo.util.hostify(args.address)
        self.me = bebo.util.my_addresses(self.name)
        if self.address != '0.0.0.0':
            self.me.add(self.address)
        self.hex_mode = bebo.util.get_boolean_env('HEX_MODE', args.hex_mode)

        fmt = f'{self.address} %(asctime)s %(name)s %(levelname)s %(message)s'
        if self.debug:
            level = logging.DEBUG
        else:
            level = logging.INFO
        log_kwargs = {'level': level, 'format': fmt}
        if args.logfile:
            log_kwargs['filename'] = f'{self.address}.log'
        self.bebo_port = args.port
        self.http_port = args.http_port
        logging.basicConfig(**log_kwargs)  # type: ignore
        log = logging.getLogger('bebo.main')
        self.version = bebo.util.get_version(args.debug)
        log.info('starting bebo ' + self.version)
        neighbor_names = []
        if len(args.neighbors) > 0:
            neighbor_names = args.neighbors
        elif 'NEIGHBORS' in os.environ:
            ntext = os.environ['NEIGHBORS'].replace(' ', '')
            neighbor_names = ntext.split(',')
        self.neighbor_names = neighbor_names

        async with trio.open_nursery() as nursery:
            # We turn off debug and especially the surprising use_reloader
            # feature of Quart.
            nursery.start_soon(app.run_task, self.address, self.http_port,
                               False, False)
            nursery.start_soon(functools.partial(trio.serve_tcp,
                                                 host=self.address),
                               self.reader, 0xbeb0)
            nursery.start_soon(self.periodic_purger)
            nursery.start_soon(self.resolver, nursery)

db = bebo.storage.Storage()
server = Server(db)
app = quart_trio.QuartTrio('bebo')

@app.route('/uuid')
async def uuid():
    return quart.jsonify({'uuid': db.uuid}), 200

@app.route('/connected')
async def connected():
    return f'{server.connected_neighbors}', 200

@app.route('/servers')
async def servers():
    servers = set(server.me)
    for n in server.neighbors.values():
        servers.add(n.address)
    return quart.jsonify({'servers': sorted(list(servers))}), 200


@app.route("/")
async def index_page():
    version = server.version
    if version is None:
        version = 'N/A'
    if db.next_sequence_number > 1:
        first = max(db.next_sequence_number - 50, 1)
        messages = db.get_range(first, 50)
    else:
        messages = []
    try:
        messages = [(i, bebo.decode.kind(m.message)) for i, m in messages]
    except Exception:
        messages = [(i, 'unknown') for i, m in messages]
    return await quart.render_template(
        'index.html',
        name='complete ' + os.getenv("NAME", "world"),
        hostname=socket.gethostname(),
        version=version,
        db=db,
        msgs=messages,
        last_update_time=time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()))

#
# This is a legacy bebo API
#

@app.route('/messages/nextsequence')
async def nextsequence():
    return f'{db.next_sequence_number}', 200


#
# This is the existing whiteboard API.
#

@app.route('/messages/write/', methods=['POST'])
async def write():
    data = await quart.request.get_data()
    (seqno, _) = await server.inject(bebo.protocol.RelayMessage(data, True))
    return quart.jsonify({'messageId': seqno}), 201

@app.route('/messages/writeWithTimeout/<float:timeout_mins>/', methods=['POST'])
async def write_with_timeout(timeout_mins=0):
    # XXXRTH we just ignore the timeout as our store doesn't do
    # time-based expiration.
    data = await quart.request.get_data()
    (seqno, _) = await server.inject(bebo.protocol.RelayMessage(data, True))
    timeout_secs = int(float(timeout_mins) * 60)
    return quart.jsonify({'messageId': seqno, 'timeoutSecs': timeout_secs}), 201

@app.route('/flush')
async def flush():
    db.flush()
    return quart.redirect(quart.url_for('index_page'))

@app.route('/messages/readone/<int:sequence_number>')
def readone(sequence_number):
    message = db.get_by_sequence_number(sequence_number)
    if message:
        resp = quart.Response(message.message, status=200)
        resp.mimetype = message.mime_type()
        return resp
    else:
        quart.abort(404)

def create_requester_id(request):
    return f"{request.environ['REMOTE_ADDR']}:{request.environ['REMOTE_PORT']}"

@app.route('/messages/read/')
def read():
    listener_id = create_requester_id(quart.request)
    return readFrom(listener_id)

@app.route('/messages/read/<listener_id>')
def readFrom(listener_id):
    messages = db.messages_for_id(listener_id)
    if len(messages) > 0:
        status = 200
    else:
        status = 204
    # XXXRTH To be compatible with the API we're returning an empty
    # JSON list in the 204 situation, but the rules for 204 say that
    # the message body MUST NOT contain a body.  Probably we should
    # just always return 200 because an empty list is a perfectly fine
    # success result.
    return quart.jsonify([(message.mime_type(), message.to_json(), '')
                          for message in messages]), status

@app.route('/messages/explain/<int:seqno>', methods=['GET'])
async def decode(seqno):
    message = db.get_by_sequence_number(seqno)
    if not server.hex_mode:
        try:
            decoded = bebo.decode.explain(message.message)
            return quart.jsonify(decoded), 200
        except Exception:
            pass
    # either we want hex mode, or decoding failed
    decoded = bebo.util.hexdump(message.message)
    return quart.Response(decoded, mimetype='text/plain', status=200)

#
# New REST API
#

@app.route('/message', methods=['GET'])
async def new_read():
    first = quart.request.args.get('first', default=0, type=int)
    count = quart.request.args.get('count', default=1, type=int)
    count = min(count, MAX_GET_COUNT)
    messages = db.get_range(first, count)
    response = db.state()
    response['messages'] = [{'id': i,
                             'message': message.to_json()}
                            for (i, message) in messages]
    return quart.jsonify(response), 200

@app.route('/message', methods=['POST'])
async def new_write():
    data = await quart.request.get_data()
    (seqno, created) = await server.inject(bebo.protocol.RelayMessage(data,
                                                                      True))
    response = db.state()
    response['id'] = seqno
    if created:
        result = 201
    else:
        result = 200
    return quart.jsonify(response), result

#
# Main
#

def main():
    try:
        trio.run(server.main, sys.argv[1:])
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()
