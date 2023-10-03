#  Copyright (c) 2019-2023 SRI International.
from __future__ import annotations

from datetime import datetime
from jaeger_client import SpanContext
import math
import random
import structlog
import trio
from typing import List, Tuple, Optional

from .enums import *
from prism.common.transport import transport as dt
from prism.common.message import PrismMessage
from prism.common.replay import Replay
from prism.common.tracing import extract_span_context, inject_span_context
from .rest_api import RestAPI


class BeboChannel(dt.Channel):
    def __init__(self, configuration, url_proxy_pairs: List[Tuple[str, Optional[str]]], replay: Replay):
        super().__init__("prism/bebo")

        # set meaningful attributes
        self.replay = replay
        self.status = ChannelStatus.UNDEF
        self.link_direction = LinkDirection.BIDI
        self.transmission_type = TransmissionType.MULTICAST
        self.connection_type = ConnectionType.INDIRECT
        self.reliable = False
        self.mtu = 0
        self.latency_ms = 50
        self.bandwidth_bps = 1000000
        self.loss = 0.0

        # create link objects for requested subset (choose randomly)
        indices = range(len(url_proxy_pairs))
        redundancy = configuration.get("wbs_redundancy", len(url_proxy_pairs))
        if max(redundancy, 0) < len(url_proxy_pairs):
            # down-select from given possible links:
            indices = random.choices(indices, k=redundancy)
        self._links = {url: BeboLink(configuration, url, proxy, self) for url, proxy in
                       [url_proxy_pairs[i] for i in indices]}

        self._logger = structlog.get_logger(__name__ + f" {__class__}")
        self._logger.info(f'Adding BEBO with links: {self.links}')

    @property
    def links(self) -> List[BeboLink]:
        return list(self._links.values())

    # TODO: whether to report all existing links back if endpoint starts with "*"?
    # async def create_links(self, endpoints: List[str]) -> List[BeboLink]:
    #     if all(ep.startswith("*") for ep in endpoints):
    #         return self.links
    #     return []


class BeboLink(dt.Link, RestAPI):
    def __init__(self, configuration, url: str, proxy: str, channel: BeboChannel):
        super().__init__(f"{channel.channel_id}/{url}", "genesis")
        self.configuration = configuration
        self.channel: BeboChannel = channel
        self.endpoints = ["*client"]  # always anonymous broadcast
        self.link_type = LinkType.BIDI
        self.connection_status = ConnectionStatus.AVAILABLE

        self.link_address = url
        self.proxy = {'http': proxy, 'https': proxy} if proxy else None

        self._logger = structlog.get_logger(__name__ + f" {__class__}")

    async def start_polling(self, send_channel: trio.MemorySendChannel):
        assert send_channel

        offset = random.random() * self.configuration.wbs_poll_time * 60
        self._logger.debug(f"Starting poller of whiteboard {self.link_address} after {offset:.2f}s", seconds=offset)
        await trio.sleep(offset)  # stagger multiple pollers

        async with send_channel:
            async for data, _ in self.get_data(self.link_address, self.proxy, "wbs_poll_time",
                                               self.configuration.wbs_polling_timeout_secs,
                                               max(1, self.configuration.wbs_polling_batch_size)):
                # self._logger.debug(f'got message', digest=hash_data(data))
                try:
                    msg = PrismMessage.decode(data)
                    context = extract_span_context(msg)
                    if context:
                        trace = context.trace_id
                    else:
                        trace = None
                    pkg = dt.Package(msg, context, datetime.utcnow(), link=self)
                    self.channel.replay.log_receive([self], data, trace)
                    self.last_receive = datetime.utcnow()
                    await send_channel.send(pkg)
                except Exception as e:
                    self._logger.warning(f"Could not decode data of len={len(data)} as PrismMessage: {e}")

    async def send(self, message: PrismMessage, context: SpanContext = None, timeout_ms: int = math.inf) -> bool:
        if context:
            trace = context.trace_id
            message = inject_span_context(message, context)
        else:
            trace = None
        data = message.encode()
        with trio.move_on_after(timeout_ms / 1000):
            success = await self.post_data(self.link_address, self.proxy, message.encode(),
                                           self.configuration.wbs_posting_timeout_secs)
            self.channel.replay.log("*", self, data, trace, None)

        if success:
            self.last_send = datetime.utcnow()
        return success

    def can_reach(self, address: str) -> bool:
        return self.configuration.get("is_client", False) or super().can_reach(address)
