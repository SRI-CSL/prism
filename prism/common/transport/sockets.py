#  Copyright (c) 2019-2023 SRI International.
from __future__ import annotations

from datetime import datetime

from jaeger_client import SpanContext
import math
from random import random
import structlog
import trio
from typing import List, Dict, Optional

import prism.common.transport.transport as dt
from .enums import *
from prism.common.message import PrismMessage
from .terminated_frame import TerminatedFrameReceiver
from prism.common.replay import Replay
from prism.common.tracing import extract_span_context, inject_span_context


class SocketsChannel(dt.Channel):

    def __init__(self, configuration, committee_members: List[str], own_index: int, replay: Replay):
        super().__init__("prism/socket")
        self.configuration = configuration
        self.replay = replay

        # set meaningful attributes
        self.status = ChannelStatus.UNDEF
        self.link_direction = LinkDirection.LOADER_TO_CREATOR
        self.transmission_type = TransmissionType.UNICAST
        self.connection_type = ConnectionType.DIRECT
        self.reliable = True
        self.mtu = 0
        self.latency_ms = 10
        self.bandwidth_bps = 1000000
        self.loss = 0.0

        # create Link objects for remote members (send) and myself (recv):
        self._links = {}  # type: Dict[str, SocketsLink]
        own_address = committee_members[own_index]  # this should fail if we have index outside of list!
        self._links[own_address] = SocketsReceiveLink(configuration, own_address, self)
        for remote_address in committee_members[:own_index] + committee_members[own_index + 1:]:
            self._links[remote_address] = SocketsSendLink(configuration, remote_address, self)

        self._logger = structlog.get_logger(__name__ + f" {__class__}")

    @property
    def links(self) -> List[SocketsLink]:
        return list(self._links.values())


class SocketsLink(dt.Link):
    terminator = b"\r\nPRISM-BARRIER\r\n"

    def __init__(self, configuration, address: str, channel: SocketsChannel):
        super().__init__(f"{channel.channel_id}/{address}", "genesis")
        self.configuration = configuration
        self.channel: SocketsChannel = channel
        self.endpoints = [address]
        self.connection_status = ConnectionStatus.UNAVAILABLE  # or AWAITING_CONTACT?
        self.link_address = address
        self._logger = structlog.get_logger(__name__ + f" {self.__class__.__name__}")

    async def start(self, forward_ch: trio.MemorySendChannel):
        pass


class SocketsSendLink(SocketsLink):
    def __init__(self, configuration, address: str, channel: SocketsChannel):
        super().__init__(configuration, address, channel)
        self.link_type = LinkType.SEND
        self.peer_address = (address, self.configuration.prism_socket_port)
        self._logger = self._logger.bind(peer=self.peer_address)

        self.in_channel, self.out_channel = trio.open_memory_channel(0)
        self.reconnecting = False

    async def start(self, forward_ch: trio.MemorySendChannel):
        while True:
            self.connection_status = ConnectionStatus.OPEN
            sock = await self.connect()
            async with trio.SocketStream(sock) as client_stream:
                # now kick off sending to this peer:
                async for pkg in self.out_channel:
                    (data, evt) = pkg
                    if await self.test_consume():
                        continue
                    try:
                        await client_stream.send_all(data + SocketsLink.terminator)
                        evt.set()
                    except trio.BusyResourceError as e:
                        self._logger.warning(f'Could not send data due to: {e}, but keep going after short sleep')
                        await self.in_channel.send(pkg)
                        await trio.sleep(1.0)
                    except trio.BrokenResourceError as e:
                        self._logger.warning(f'Could not send data due to: {e}, stopping')
                        await self.in_channel.send(pkg)
                        break
            self.connection_status = ConnectionStatus.UNAVAILABLE
            self._logger.debug(f'Gearing up to re-connect to peer(s) {self.endpoints} at {self.peer_address}')
            self.reconnecting = True

    async def connect(self) -> trio.socket:
        self._logger.debug(
            f'{"re-" if self.reconnecting else ""}connecting with peer(s) {self.endpoints} at {self.peer_address}...')
        while True:
            sock = trio.socket.socket()
            sleep_time = self.configuration.get('tcp_socket_reconnect_after', 5.0)
            try:
                with trio.move_on_after(sleep_time) as cancel_scope:
                    await sock.connect(self.peer_address)

                if cancel_scope.cancelled_caught:
                    self._logger.warning(f'Could not connect within with peer(s)' +
                                         f' at {self.peer_address} in {sleep_time:.2f}s')
                    sock.close()
                else:
                    self._logger.debug(f'successfully connected with peer(s) {self.endpoints} at {self.peer_address}')
                    return sock
            except (ConnectionRefusedError, OSError) as e:
                self._logger.warning(f'Re-connecting with peer(s) {self.endpoints} at {self.peer_address} ' +
                                     f'after {sleep_time:.2f}s due to {e}')
                await trio.sleep(sleep_time)

    async def test_consume(self) -> bool:
        # anything >= 1 will drop ALL packages
        testing_drop = self.configuration.get('socket_test_drop', 0.0)
        if random() < testing_drop:
            self._logger.debug(f'[TEST] Dropping data due to testing rate {int(testing_drop * 100)}%')
            return True

        testing_delay = self.configuration.get('socket_test_delay', 0.0)
        if testing_delay > 0:  # add random delay
            testing_delay = random() * testing_delay
        elif testing_delay < 0:  # add fixed delay
            testing_delay *= -1
        if testing_delay > 0:
            self._logger.debug(f'[TEST] Delaying sending by {testing_delay:.2f}s')
        await trio.sleep(testing_delay)

        return False

    async def send(self, message: PrismMessage, context: SpanContext = None, timeout_ms: int = math.inf) -> bool:
        with trio.move_on_after(timeout_ms / 1000):
            success = trio.Event()
            if context:
                trace = context.trace_id
                message = inject_span_context(message, context)
            else:
                trace = None
            data = message.encode()
            await self.in_channel.send((data, success))
            await success.wait()
            self.channel.replay.log(self.endpoints[0], self, data, trace, None)
            self.last_send = datetime.utcnow()
            return True
        return False


class SocketsReceiveLink(SocketsLink):
    def __init__(self, configuration, address: str, channel: SocketsChannel):
        super().__init__(configuration, address, channel)
        self.link_type = LinkType.RECV
        self.listen_port = self.configuration.prism_socket_port
        self._logger = self._logger.bind(port=self.listen_port)

        self.forward_channel: Optional[trio.MemorySendChannel] = None

    async def handle_connection(self, server_stream):
        remote_address = server_stream.socket.getpeername()
        self._logger.info(f'TCP connection from {remote_address} established')
        async with self.forward_channel.clone() as forward_channel:
            # TODO: if we want to catch unexpected exceptions here then use try-except construct; see:
            #  https://trio.readthedocs.io/en/stable/tutorial.html#an-echo-server
            framed_stream = TerminatedFrameReceiver(server_stream, terminator=SocketsLink.terminator)
            async for frame in framed_stream:
                try:
                    message = PrismMessage.decode(frame)
                    context = extract_span_context(message)
                    if context:
                        trace = context.trace_id
                    else:
                        trace = None
                    pkg = dt.Package(message, context, datetime.utcnow(), link=self)
                    self.channel.replay.log_receive([self], frame, trace)
                    self.last_receive = datetime.utcnow()
                    await forward_channel.send(pkg)
                except Exception as e:
                    self._logger.warning(f"Could not decode data of len={len(frame)} as PrismMessage: {e}")
                # TODO: Linda: need to handle trio.ClosedResourceError when things time out?
        self._logger.info(f'TCP connection from {self.endpoints} {remote_address} closed')

    async def start(self, forward_ch: trio.MemorySendChannel):
        assert forward_ch
        self.forward_channel = forward_ch
        self.connection_status = ConnectionStatus.AVAILABLE
        await trio.serve_tcp(self.handle_connection, self.listen_port)

    async def send(self, message: PrismMessage, context: SpanContext = None, timeout_ms: int = math.inf) -> bool:
        return False  # cannot send on receive link
