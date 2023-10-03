#  Copyright (c) 2019-2023 SRI International.
import structlog
import trio
from typing import List, Optional

from .bebo import BeboChannel
from .transport import Transport, Channel
from prism.common.deduplicate import MessageDeduplicator
from .sockets import SocketsChannel
from prism.common.replay import Replay


class PrismTransport(Transport):
    def __init__(self, configuration):
        super().__init__(configuration)
        self.configuration = configuration
        self.bebo: Optional[BeboChannel] = None
        self.tcp_channel: Optional[SocketsChannel] = None
        self.replay = None
        self._logger = structlog.get_logger(__name__)
        self._configure()

    def _configure(self):
        # override local address if name is given:
        local_address = self.configuration.get('name', None)
        if local_address:
            self.local_address = local_address
        self._logger = self._logger.bind(local_address=self.local_address)
        self.replay = Replay(self.local_address or "local", self.configuration.get("log_dir"))

        if self.configuration.get('whiteboards'):
            # now parse the parameters pertaining to multiple whiteboards, their proxies (if given), and redundancy
            whiteboards = self.configuration.get("whiteboards", [])
            proxy_str = self.configuration.get('http_proxies')
            proxies = None
            if proxy_str:
                proxies = [item.strip() if len(item.strip()) > 0 else None for item in proxy_str.split(',')]
                if not len(proxies) == len(whiteboards):
                    self._logger.warning(
                        'Configured proxies are not the same length as whiteboard URLs - ignoring all proxies!')
                    proxies = None
            if not proxies:
                proxies = [None] * len(whiteboards)
            url_proxy_pairs = [(wb, proxy) for wb, proxy in zip(whiteboards, proxies)]
            self.bebo = BeboChannel(self.configuration, url_proxy_pairs, self.replay)

        committee_str = self.configuration.get('committee_members', None)
        party_id = self.configuration.get('party_id', -1)
        if committee_str and party_id >= 0:
            self.tcp_channel = SocketsChannel(self.configuration, committee_str.split(','), party_id, self.replay)

        self._logger.info(f"Configured {self}")

    def __str__(self):
        return f"Prism Transport (channels: {self.channels})"

    @property
    def channels(self) -> List[Channel]:
        return [ch for ch in [self.bebo, self.tcp_channel] if ch is not None]

    async def forward_to_hooks(self, receive_channel: trio.MemoryReceiveChannel, nursery: trio.Nursery):
        self._logger.debug(f"Starting task to forward packages to hooks")
        seen = MessageDeduplicator(self.configuration)
        nursery.start_soon(seen.purge_task)
        async with receive_channel:
            async for pkg in receive_channel:
                if not seen.is_msg_new(pkg.message):
                    continue
                await self.submit_to_hooks(pkg)

    async def run(self):
        self.replay.start()
        send_ch, recv_ch = trio.open_memory_channel(0)
        async with trio.open_nursery() as nursery:
            nursery.start_soon(super().run)
            nursery.start_soon(self.forward_to_hooks, recv_ch, nursery)
            if self.bebo:
                for bebo_link in self.bebo.links:
                    nursery.start_soon(bebo_link.start_polling, send_ch.clone())
            if self.tcp_channel:
                for tcp_link in self.tcp_channel.links:
                    nursery.start_soon(tcp_link.start, send_ch.clone())
