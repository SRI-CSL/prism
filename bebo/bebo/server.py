#  Copyright (c) 2019-2023 SRI International.

import argparse
import functools
import logging
import os
import socket
import struct
import sys
import time

import dns.asyncresolver
import dns.inet
import quart
import quart_trio
import trio           # type: ignore
import trio.socket    # type: ignore

import bebo.decode
import bebo.lruqueue
import bebo.protocol
import bebo.seeds
import bebo.storage
import bebo.util

from typing import Dict, Iterable, List, Optional, Set, Tuple, Union

IPAddress = Union[Tuple[str, int], Tuple[str, int, int, int]]

BEBO_PORT = 0xbeb0
NEIGHBOR_NOTIFIER_WAKE_TIMEOUT = 10    # artificially low for testing
IGNORE_INTERVAL = 300
IGNORE_PURGE_INTERVAL = 300
MAX_GET_COUNT = 100
RESOLUTION_INTERVAL = 60
STARTUP_RESOLUTION_INTERVAL = 5
STARTUP_INTERVAL = 120

class Neighbor:
    def __init__(self, address: str, neighbors: Optional[Iterable[str]]=None):
        self.address = address
        if neighbors is None:
            neighbors = []
        self.neighbors = set(neighbors)
        self.send_channel = None
        self.receive_channel = None
        self.canceled = False
        self.available = False

    def update_neighbors(self, other):
        assert self.address == other.address
        self.neighbors = set(other.neighbors)

    def cancel(self):
        self.canceled = True

    async def setup_channels(self):
        # copy the channel references so we can set them to None, as we
        # can block closing and we don't want someone to try to (say)
        # send to the send_channel.  It might be better if we had things
        # wait on a "channel ready" event or something.  Being able to flush
        # a channel would be nice, but this doesn't seem possible.
        sc = self.send_channel
        self.send_channel = None
        rc = self.receive_channel
        self.receive_channel = None
        if sc:
            await sc.aclose()
        if rc:
            await rc.aclose()
        (self.send_channel, self.receive_channel) = trio.open_memory_channel(10000)

    def __str__(self):
        return f'neighbor {self.address}'

async def read_exactly(stream, count: int) -> bytes:
    s = b''
    while count > 0:
        n = await stream.receive_some(count)
        if n == b'':
            raise EOFError
        count = count - len(n)
        s = s + n
    return s

class Server:
    def __init__(self, db: bebo.storage.Storage):
        self.db = db
        self.neighbors: Dict[str, Neighbor] = {}
        self.connected_neighbors: int = 0
        self.wake_notifier = trio.Condition()
        self.mpr: Optional[Set[str]] = set()
        self.seeds = bebo.seeds.Seeds()
        # The blocking limit on the channel has to be less than the number of
        # initial neighbors or we can deadlock at startup
        (self.send_neighbor_channel, self.receive_neighbor_channel) = \
            trio.open_memory_channel(10)
        self.cancel_scopes: Dict[str, List[trio.CancelScope]] = {}
        # Ignored peers are ignored until the specified time.
        self.ignored_peers: Dict[str, float] = {}
        self.me: Set[str] = set()
        self.version = None

    def is_me(self, address: str) -> bool:
        return address in self.me

    def is_ignored(self, address: str) -> bool:
        when = self.ignored_peers.get(address)
        if when and trio.current_time() < when:
            return True
        else:
            return False

    def peer_allowed(self, address: str) -> bool:
        if self.is_ignored(address):
            return False
        return True

    def add_cancel_scope(self, peer, scope):
        scopes = self.cancel_scopes.get(peer)
        if not scopes:
            scopes = []
            self.cancel_scopes[peer] = scopes
        scopes.append(scope)

    def cancel_peer(self, peer):
        scopes = self.cancel_scopes.get(peer)
        if scopes:
            del self.cancel_scopes[peer]
            for scope in scopes:
                scope.cancel()

    async def delete_neighbor(self, address: str) -> bool:
        neighbor = self.neighbors.get(address)
        if neighbor:
            await self.send_neighbor_channel.send((neighbor, True))
            return True
        else:
            return False

    async def handshake(self, stream, error=None) -> Optional[str]:
        with trio.move_on_after(10):
            data = bebo.protocol.HandshakeMessage(error).to_cbor()
            l = len(data)
            packet = struct.pack("!I", l) + data
            await stream.send_all(packet)
            data = await read_exactly(stream, 4)
            (l,) = struct.unpack('!I', data)
            data = await read_exactly(stream, l)
            if data:
                message = bebo.protocol.from_cbor(data)
                if isinstance(message, bebo.protocol.HandshakeMessage):
                    return message.error
            return 'did not get a return HandshakeMessage'
        return 'handshake timed out'

    async def reader(self, stream) -> None:
        log = logging.getLogger('bebo.reader')
        peer = stream.socket.getpeername()
        our_error = None
        if self.is_me(peer[0]):
            log.error('rejecting connection from my own host: %s', peer)
            our_error = 'connection from myself'
        elif not self.peer_allowed(peer[0]):
            log.error('peering not allowed: %s', peer)
            our_error = 'peering not allowed'
        their_error = await self.handshake(stream, our_error)
        if our_error or their_error:
            if their_error:
                log.error('peer handshake error: %s %s', peer, their_error)
            return

        with trio.CancelScope() as scope:
            self.add_cancel_scope(peer[0], scope)
            log.info('%s:%d connected', peer[0], peer[1])
            stream.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            try:
                while True:
                    data = await read_exactly(stream, 4)
                    (l,) = struct.unpack('!I', data)
                    data = await read_exactly(stream, l)
                    if data:
                        message = bebo.protocol.from_cbor(data)
                        log.debug('%s:%d received %s', peer[0], peer[1],
                                  message.key())
                        if isinstance(message, bebo.protocol.RelayMessage):
                            neighbor = self.neighbors.get(peer[0])
                            await self.inject(message, neighbor)
                        elif isinstance(message,
                                        bebo.protocol.NeighborsMessage):
                            neighbor = Neighbor(peer[0],
                                                [x for x in message.neighbors
                                                 if not self.is_me(x)])
                            await self.send_neighbor_channel.send((neighbor,
                                                                   False))
                        else:
                            logging.error('unhandled message', message, 'from',
                                          peer)
                    else:
                        logging.debug('%s:%d EOF', peer[0], peer[1])
                        break
            except Exception:
                log.error('%s:%d caught exception %s', peer[0], peer[1],
                          sys.exc_info()[0])
            log.info('%s:%d disconnected', peer[0], peer[1])

    async def sender(self, neighbor: Neighbor) -> None:
        with trio.CancelScope() as scope:
            self.add_cancel_scope(neighbor.address, scope)
            log = logging.getLogger('bebo.sender')
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
                    af = bebo.util.af_for_text_address(neighbor.address)
                    if af == socket.AF_INET:
                        lsa: IPAddress = (self.host, 0)
                        psa: IPAddress = (neighbor.address, self.port)
                    else:
                        lsa = (self.host, 0, 0, 0)
                        psa = (neighbor.address, self.port, 0, 0)
                    s = trio.socket.socket(af)
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    await s.bind(lsa)
                    await s.connect(psa)
                    stream = trio.SocketStream(s)
                    backoff = 1
                    connected = True
                    self.connected_neighbors += 1
                    log.info('%s connected', neighbor)
                    async with stream:
                        assert neighbor.receive_channel is not None
                        done = False
                        their_error = await self.handshake(stream)
                        if their_error:
                            log.debug('%s handshake error %s', neighbor,
                                      their_error)
                            await self.delete_neighbor(neighbor.address)
                            done = True
                            retry = False
                        neighbor.available = True
                        while not done:
                            message = await neighbor.receive_channel.receive()
                            log.debug('%s sending %s', neighbor, message)
                            data = message.to_cbor()
                            l = len(data)
                            packet = struct.pack("!I", l) + data
                            await stream.send_all(packet)
                except ConnectionError:
                    log.debug('%s caught connection exception %s', neighbor,
                              sys.exc_info()[0])
                except Exception as exp:
                    log.error(f'{neighbor} caught exception {exp}')
                finally:
                    # We do this here so the count is right even if we
                    # get canceled.
                    if connected:
                        self.connected_neighbors -= 1
                    neighbor.available = False
                    self.compute_mpr()
                # Close existing channels and make new ones, thus flushing
                # any queued messages.  We do it this way as it is safe;
                # if we just tried to drain the queue we might never stop
                # if someone else was producing.
                await neighbor.setup_channels()
                if connected:
                    connected = False
                    log.info('%s disconnected', neighbor)
                else:
                    log.debug('%s connection failed, backoff = %d', neighbor,
                              backoff)
                await trio.sleep(backoff)
                backoff = min(2 * backoff, 32)
            log.debug('%s finished', neighbor)

    async def neighbor_maintenance(self, nursery) -> None:
        log = logging.getLogger('bebo.neighbor_maintenance')
        last_ignored_purge = 0
        while True:
            try:
                updated_neighbor: Neighbor
                (updated_neighbor, is_delete) = \
                    await self.receive_neighbor_channel.receive()
                now = trio.current_time()
                if now - last_ignored_purge >= IGNORE_PURGE_INTERVAL:
                    log.debug('periodic ignored peers purge')
                    peers_to_purge = []
                    for (peer, when) in self.ignored_peers.items():
                        if when >= now:
                            peers_to_purge.append(peer)
                    for peer in peers_to_purge:
                        del self.ignored_peers[peer]
                    last_ignored_purge = now
                recompute = True
                if is_delete:
                    # Delete the neighbor (if we haven't already done it).
                    neighbor = self.neighbors.get(updated_neighbor.address)
                    if not neighbor or neighbor.canceled:
                        continue
                    log.info('deleted neighbor %s', neighbor.address)
                    self.cancel_peer(neighbor.address)
                    del self.neighbors[neighbor.address]
                    self.ignored_peers[neighbor.address] = \
                        trio.current_time() + IGNORE_INTERVAL
                    async with self.wake_notifier:
                        self.wake_notifier.notify_all()
                else:
                    # Add or update the neighbor
                    neighbor = self.neighbors.get(updated_neighbor.address)
                    if neighbor:
                        if neighbor.neighbors != updated_neighbor.neighbors:
                            # neighbor's neighbors changed; update the state in
                            # the existing neighbor object.
                            log.debug('neighbor %s changed',
                                      updated_neighbor.address)
                            neighbor.update_neighbors(updated_neighbor)
                            # And wake up the notifier so we don't sit on
                            # the change.
                            async with self.wake_notifier:
                                self.wake_notifier.notify_all()
                        else:
                            # we already know all this
                            log.debug('neighbor %s unchanged',
                                      updated_neighbor.address)
                            recompute = False
                    else:
                        log.info('new neighbor %s', updated_neighbor.address)
                        # This is a new neighbor
                        self.neighbors[updated_neighbor.address] = \
                            updated_neighbor
                        neighbor = updated_neighbor
                        await neighbor.setup_channels()
                        nursery.start_soon(self.sender, neighbor)
                        async with self.wake_notifier:
                            self.wake_notifier.notify_all()
                if recompute:
                    self.compute_mpr()
            except Exception:
                log.error('caught exception %s', sys.exc_info()[0])

    def compute_mpr(self) -> None:
        if self.no_mpr:
            self.mpr = None
            return
        # First get one hop addresses
        one_hop = {n.address for n in self.neighbors.values() if n.available}
        # Now compute the "strict" two hop addresses, which are ...
        strict_two_hop = set()
        neighbors_of: Dict[str, List[str]] = {}
        # ... all of the addresses of the neighbors of our neighbors ...
        for x in self.neighbors.values():
            if not x.available:
                continue
            strict_two_hop.update(set(x.neighbors))
            # we also will want to know who all the neighbors of a particular
            # two-hop neighbor are
            for y in x.neighbors:
                n = neighbors_of.get(y)
                if n is None:
                    n = []
                    neighbors_of[y] = n
                n.append(x.address)
        # ... but not the addresses of our neighbors (some our neighbors
        # might be neighbors of each other) ...
        for y in one_hop:
            strict_two_hop.discard(y)
        # ... and not our address
        strict_two_hop.discard(self.host)
        log = logging.getLogger('bebo.mpr')
        log.debug('strict two-hop %s', repr(strict_two_hop))

        self.mpr = set()
        # We have to accumulate removals to avoid breaking our iterator
        remove = set()
        for z in strict_two_hop:
            n = neighbors_of[z]
            if len(n) == 1:
                # This node only has one neighbor.
                y = n[0]
                # Which must be a one hop neighbor!
                assert y in one_hop
                log.debug('mpr add one-neighbor %s', y)
                self.mpr.add(y)
                # we've dealt with isolated two-hop neighbor z by
                # adding one-hop neighbor y, so remove z from
                # strict_two_hop (i.e. strict_two_hop is really the
                # "strict two-hops we haven't handled yet" set.
                remove.add(z)
                log.debug('mpr remove one-neighbor %s', z)
                # also, by adding y to the MPR we've covered all of
                # its neighbors, so remove any of them from
                # strict_two_hop as well.
                remove.update(self.neighbors[y].neighbors)
                log.debug('mpr remove one-neighbor neighbors %s',
                          self.neighbors[y].neighbors)
        # Apply the accumulated removals.
        strict_two_hop = strict_two_hop.difference(remove)
        # Now repeatedly add the neighbor that covers the most two hop
        # neighbors to the MPR set until all the two hop neighbors are
        # covered.
        while len(strict_two_hop) > 0:
            max_node: Optional[str] = None
            max_count: int = 0
            max_covered: Set[str] = set()
            for y in one_hop:
                if y in self.mpr:
                    continue
                y_neighbors = self.neighbors[y].neighbors
                covered = set(y_neighbors).intersection(strict_two_hop)
                count = len(covered)
                if count > max_count:
                    max_count = count
                    max_node = y
                    max_covered = covered
            assert max_node is not None
            log.debug('max-node %s %s', max_node, max_covered)
            self.mpr.add(max_node)
            strict_two_hop = strict_two_hop.difference(max_covered)
        if len(self.mpr) == 0:
            self.mpr = None
        log.info('updated to %s', self.mpr)

    async def neighbor_notifier(self) -> None:
        log = logging.getLogger('bebo.neighbor_notifier')
        while True:
            try:
                addresses = list(x.address for x in self.neighbors.values()
                                 if x.available)
                log.debug(addresses)
                with trio.move_on_after(NEIGHBOR_NOTIFIER_WAKE_TIMEOUT):
                    async with self.wake_notifier:
                        await self.wake_notifier.wait()
                await self.inject(bebo.protocol.NeighborsMessage(addresses))
            except Exception:
                log.error('caught exception %s: %s', sys.exc_info()[0],
                          sys.exc_info()[1])

    async def periodic_purger(self) -> None:
        while True:
            await trio.sleep(10)
            self.db.purge()

    async def inject(self, message: bebo.protocol.Message,
                     originator: Optional[Neighbor]=None):
        #
        # Inject a message into the network.  Returns a (seqno, created)
        # tuple.  Created is true iff. the message was not in storage
        # already when injected.
        #
        log = logging.getLogger('bebo.inject')
        seqno = 0
        want_broadcast = message.broadcast
        existing = None
        if isinstance(message, bebo.protocol.RelayMessage):
            # Add (or retrieve) the message from the database
            (existing, seqno) = self.db.add(message)
            if existing:
                if existing.broadcast:
                    # We've seen it and sent it already.
                    want_broadcast = False
                elif want_broadcast:
                    # We've seen it before, haven't sent it before, and want
                    # to send it now.  Remember that so we don't send it again
                    # later.
                    existing.broadcast = True
        log.debug('inject %s broadcast = %s', message.key(), want_broadcast)
        if want_broadcast:
            # we can block sending and someone could change neighbors,
            # breaking our iterator, so make a copy of the current
            # neighbors
            copied = [x for x in self.neighbors.values()]
            for neighbor in copied:
                if isinstance(message, bebo.protocol.RelayMessage):
                    # set broadcast for the message sent to this neighbor
                    # based on its MPR status
                    if self.no_mpr or self.mpr is None:
                        do_broadcast = True
                    else:
                        do_broadcast = neighbor.address in self.mpr
                    out_message: bebo.protocol.Message = \
                        bebo.protocol.RelayMessage(message.message,
                                                   do_broadcast)
                else:
                    out_message = message
                if neighbor != originator and neighbor.send_channel:
                    await neighbor.send_channel.send(out_message)
        return (seqno, existing is None)

    async def resolver(self, neighbor_names, v4_ok=True, v6_ok=True):
        log = logging.getLogger('bebo.resolver')
        # maybe work around dnspython bug!
        res = dns.asyncresolver.get_default_resolver()
        res.ndots = None
        start_time = time.time()
        while True:
            log.debug('resolver awake')
            for name in neighbor_names:
                rdtypes = []
                if v6_ok:
                    rdtypes.append('AAAA')
                if v4_ok:
                    rdtypes.append('A')
                address = None
                for rdtype in rdtypes:
                    try:
                        answer = await res.resolve(name, rdtype, search=True)
                        for rr in answer:
                            address = rr.address
                            # pick first address only
                            break
                    except Exception as e:
                        log.debug('%s %s resolution raised %s', name, rdtype, e)
                    if address is not None:
                        break
                if address is not None:
                    # found something!
                    neighbor = self.neighbors.get(address)
                    if neighbor is None:
                        try:
                            self.send_neighbor_channel.send_nowait((Neighbor(address), False))
                        except trio.WouldBlock:
                            log.debug('dropping message to neighbor %s as queue would block', neighbor.address)
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

    async def main(self, argv: List[str]):
        parser = argparse.ArgumentParser(description='bebo server')
        parser.add_argument('--address', '-a', metavar='ADDRESS',
                            default='0.0.0.0',
                            help='the address to listen on')
        parser.add_argument('--port', '-p', metavar='PORT', type=int,
                            default=BEBO_PORT,
                            help='the address to listen on')
        parser.add_argument('--http-port', '-P', metavar='PORT', type=int,
                            default=bebo.util.HTTP_PORT,
                            help='the port to serve on')
        parser.add_argument('neighbors', metavar='SERVER', nargs='*',
                            help='a bebo neighbor')
        parser.add_argument('--choose', '-c', metavar='N', type=int, default=2,
                            help='number of neighbors to choose randomly')
        parser.add_argument('--seeds', '-s', metavar='SEED', default='',
                            help='JSON URL or filename with neighbor seeds' +
                            'information')
        parser.add_argument('--debug', '-d', action='store_true')
        parser.add_argument('--no-mpr', '-M', action='store_true',
                            help="disable MPR optimization")
        parser.add_argument('--hex-mode', '-H', action='store_true')
        parser.add_argument('--logfile', '-L', metavar='FILENAME', default='',
                            help='log file name; uses stdout otherwise')
        args = parser.parse_args(argv)
        self.debug = bebo.util.get_boolean_env('DEBUG', args.debug)
        self.address = os.getenv('ADDRESS', args.address)
        self.port = bebo.util.get_int_env('PORT', args.port)
        self.http_port = bebo.util.get_int_env('HTTP_PORT', args.http_port)
        self.host = bebo.util.hostify(args.address)
        self.me = bebo.util.my_addresses()
        self.me.add(self.host)
        self.hex_mode = bebo.util.get_boolean_env('HEX_MODE', args.hex_mode)
        self.no_mpr = bebo.util.get_boolean_env('NO_MPR', args.no_mpr)

        format = f'{self.host} %(asctime)s %(name)s %(levelname)s %(message)s'
        if self.debug:
            level = logging.DEBUG
        else:
            level = logging.INFO
        log_kwargs = {'level': level, 'format': format}
        if args.logfile:
            log_kwargs['filename'] = f'{self.host}.log'
        logging.basicConfig(**log_kwargs)  # type: ignore
        log = logging.getLogger('bebo.main')
        log.debug(f"configured logging at level={level}")
        self.bebo_port = args.port
        self.http_port = args.http_port
        self.version = bebo.util.get_version(args.debug)
        log.info('starting bebo ' + self.version)
        initial_neighbors = []
        if len(args.neighbors) > 0:
            initial_neighbors = args.neighbors
        elif 'NEIGHBORS' in os.environ:
            ntext = os.environ['NEIGHBORS'].replace(' ', '')
            initial_neighbors = ntext.split(',')
        elif args.seeds:
            self.seeds = bebo.seeds.Seeds(args.seeds, self.host)
            initial_neighbors = self.seeds.choose(args.choose)
        elif 'SEEDS' in os.environ:
            seeds = os.environ['SEEDS'].replace(' ', '')
            # if it's not a URL, tack on "list:"
            if ':' not in seeds:
                seeds = 'list:' + seeds
            self.seeds = bebo.seeds.Seeds(seeds, self.host)
            initial_neighbors = self.seeds.choose(args.choose)
        # Queue our initial neighbors for maintenance.  Right now we take
        # them from the command line, but we could just as well pick them
        # randomly from a seed set.
        peer_names = []
        for peer in initial_neighbors:
            if peer.isdigit() or dns.inet.is_address(peer):
                peer = bebo.util.hostify(peer)
                await self.send_neighbor_channel.send((Neighbor(peer), False))
            else:
                peer_names.append(peer)
        v6_ok = bebo.util.get_boolean_env('V6_OK', True)
        log.info(f"v6_ok = {v6_ok}, initial neighbors = {initial_neighbors}, peer names = {peer_names}")
        async with trio.open_nursery() as nursery:
            # We turn off debug and especially the surprising use_reloader
            # feature of Quart.
            nursery.start_soon(app.run_task, self.host, self.http_port,
                               False, False)
            nursery.start_soon(functools.partial(trio.serve_tcp,
                                                 host=self.host),
                               self.reader, 0xbeb0)
            nursery.start_soon(self.neighbor_maintenance, nursery)
            nursery.start_soon(self.neighbor_notifier)
            nursery.start_soon(self.periodic_purger)
            nursery.start_soon(self.resolver, peer_names, True, v6_ok)

db = bebo.storage.Storage()
server = Server(db)
app = quart_trio.QuartTrio('bebo')

@app.route('/uuid')
async def uuid():
    return quart.jsonify({'uuid': db.uuid}), 200

@app.route('/connected')
async def connected():
    return f'{server.connected_neighbors}', 200

@app.route('/allneighborsnonempty')
async def allneighborsnonempty():
    if all([len(n.neighbors) > 0 for n in server.neighbors.values()]):
        return '1', 200
    else:
        return '0', 200

@app.route('/messages/nextsequence')
async def nextsequence():
    return f'{db.next_sequence_number}', 200

@app.route('/neighbor/<address>', methods=['DELETE'])
async def delete_neighbor(address):
    if await server.delete_neighbor(address):
        return '', 200
    else:
        quart.abort(404)

@app.route('/seeds')
async def seeds():
    return quart.jsonify({'seeds': list(server.seeds.all_seeds)}), 200


def is_jpeg(data):
    return (
        data.startswith(b'\xff\xd8\xff\xe0') or
        data.startswith(b'\xff\xd8\xff\xee')
    )

def kind(data):
    if is_jpeg(data):
        return 'JPEG image'
    try:
        return bebo.decode.kind(data)
    except Exception:
        return 'Unknown'

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
    messages = [(i, kind(m.message)) for i, m in messages]
    return await quart.render_template('index.html',
                                       name=os.getenv("NAME", "world"),
                                       hostname=socket.gethostname(),
                                       version=version,
                                       db=db,
                                       msgs=messages,
                                       last_update_time=
                                       time.strftime("%Y-%m-%d %H:%M:%S",
                                                     time.gmtime()))

#
# This is the existing whiteboard API.
#

@app.route('/messages/write/', methods=['POST'])
async def write():
    data = await quart.request.get_data()
    (seqno, _) = await server.inject(bebo.protocol.RelayMessage(data,
                                                                      True))
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
    if message is None:
        return quart.abort(404)
    elif server.hex_mode:
        decoded = bebo.util.hexdump(message.message)
        return quart.Response(decoded, mimetype='text/plain', status=200)
    elif is_jpeg(message.message):
        return quart.Response(message.message, mimetype='image/jpeg',
                              status=200)
    else:
        try:
            decoded = bebo.decode.explain(message.message)
        except Exception:
            decoded = bebo.util.hexdump(message.message)
            return quart.Response(decoded, mimetype='text/plain', status=200)
        return quart.jsonify(decoded), 200

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
    level = 'WARNING' if os.getenv('DEBUG', 'False').upper() == 'FALSE' else 'DEBUG'
    # from: https://pgjones.gitlab.io/quart/how_to_guides/logging.html#configuration
    from logging.config import dictConfig
    dictConfig({
        'version': 1,
        'loggers': {
            'quart.app': {'level': level},
            'quart.serving': {'level': level},
        },
    })

    main()
