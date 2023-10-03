#  Copyright (c) 2019-2023 SRI International.

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from jaeger_client import SpanContext
import math
import structlog
import trio
from typing import List, Callable, Optional, Dict, Set

from prism.common.message import PrismMessage, LinkAddress
from prism.common.tracing import extract_span_context
from .enums import *


# Represents a received package, so that the receiver gets information
# about the source of the package, in case that is relevant to them.
from ..config import configuration


@dataclass
class Package:
    message: PrismMessage
    context: SpanContext
    timestamp: datetime = field(default_factory=datetime.utcnow)
    link: Link = field(default=None)

    def __repr__(self):
        if self.link:
            return f"Package(link={self.link.link_id}, epoch={self.link.epoch})"
        else:
            return f"Package(local)"


# For local testbed, the two channels available would be "bebo" and "tcp"
class Channel:
    status: ChannelStatus
    link_direction: LinkDirection
    transmission_type: TransmissionType
    connection_type: ConnectionType
    reliable: bool
    mtu: int
    bandwidth_bps: int
    latency_ms: int
    loss: float
    tags: Set[str]

    def __init__(self, channel_id: str):
        self.channel_id = channel_id
        tags = configuration.get(f"channel_{channel_id}_tags", None)
        if tags:
            self.tags = set(tags.split(","))
        else:
            self.tags = set()

    def __repr__(self) -> str:
        attr_str = "|".join(sorted([f"{a}: {getattr(self, a)}" for a in
                                    {"status", "link_direction", "transmission_type", "connection_type", "reliable",
                                     "mtu", "bandwidth_bps", "latency_ms", "loss", "tags"}
                                    if hasattr(self, a)]))
        return f"Channel({self.channel_id}: [{attr_str}]"

    @property
    def links(self) -> List[Link]:
        return []

    async def create_link(self, endpoints: List[str], epoch: str) -> Optional[Link]:
        pass

    async def load_link(self, link_address: str, endpoints: List[str], epoch: str) -> Optional[Link]:
        pass


class Link:
    channel: Channel

    # for local testbed, a link address might look like
    # "http://bebo1:4000" or "tcp://prism-server-00003:5961"
    link_address: str

    def __init__(self, link_id: str, epoch: str):
        self.link_id = link_id
        self.epoch = epoch
        self.last_send: datetime = datetime.min
        self.last_receive: datetime = datetime.min

        # meaningful default values for expected attributes
        self.connection_status: ConnectionStatus = ConnectionStatus.CLOSED
        self.link_status: LinkStatus = LinkStatus.CREATED
        self.link_type: Optional[LinkType] = None
        # Might contain persona names, or might contain group names like "*client"
        # Can also be empty for anonymous broadcast, i.e., only supporting the "*" address
        self.endpoints: List[str] = []

    def __repr__(self) -> str:
        return f"Link({self.link_id}, {self.epoch}, {self.endpoints}, " \
               f"{self.link_type}, {self.connection_status}, {self.link_status})"

    def can_reach(self, address: str) -> bool:
        return address in self.endpoints or address == "*"

    @property
    def can_send(self) -> bool:
        return self.active and self.link_type.can_send

    @property
    def active(self) -> bool:
        return self.connection_status in [ConnectionStatus.OPEN, ConnectionStatus.AVAILABLE]

    @property
    def address_cbor(self) -> LinkAddress:
        return LinkAddress(channel_id=self.channel.channel_id, link_address=self.link_address)

    async def send(self, message: PrismMessage, context: SpanContext = None, timeout_ms: int = math.inf) -> bool:
        pass

    async def open(self):
        pass

    async def close(self):
        pass


class LocalLink(Link):
    def __init__(self, transport: Transport, epoch: str):
        super().__init__("local_link", epoch)
        self.connection_status = ConnectionStatus.OPEN
        self.link_status = LinkStatus.CREATED
        self.link_type = LinkType.SEND
        self.link_address = "local://"
        self.endpoints = ["local"]
        self.transport = transport

    async def send(self, message: PrismMessage, context: SpanContext = None, timeeout_ms: int = math.inf) -> bool:
        self.last_send = datetime.utcnow()
        self.last_receive = datetime.utcnow()
        package = Package(message, context, timestamp=datetime.utcnow(), link=self)
        await self.transport.submit_to_hooks(package)
        return True


class MessageHook:
    """A hook allows a task to register to receive specific messages inline rather than having them
    dispatched through the main message queue. Tasks should subclass MessageHook and override the
    match predicate."""
    _in: trio.MemorySendChannel
    _out: trio.MemoryReceiveChannel

    def __init__(self):
        self._in, self._out = trio.open_memory_channel(math.inf)  # unbounded so that put() doesn't block

    @property
    def in_channel(self):
        return self._in

    def dispose(self):
        """Cleans up the memory channels when the hook is unregistered."""
        self._in.close()
        self._out.close()

    # noinspection PyUnusedLocal
    def match(self, package: Package) -> bool:
        return False

    async def put(self, package: Package):
        await self._in.send(package)

    async def receive_pkg(self, timeout_ms: int = math.inf) -> Package:
        with trio.move_on_after(timeout_ms / 1000):
            return await self._out.receive()


# One object of class Transport will be provided to the server on initialization
# It will have channels preconfigured, and may or may not have links already running
class Transport:
    hooks: List[MessageHook]
    message_pool: Dict[str, Package]
    local_address: str

    def __init__(self, configuration):
        self.configuration = configuration
        self.hooks = []
        self.message_pool = {}
        self.local_address = configuration.get('name', None)
        self._logger = structlog.getLogger(__name__)
        self.local_link = LocalLink(self, "genesis")

    @property
    def overhead_bytes(self) -> int:
        return 0

    @property
    def channels(self) -> List[Channel]:
        return []

    def configure(self, **kwargs):
        pass

    def links_for_address(self, address: str) -> List[Link]:
        return [
            link for channel in self.channels for link in channel.links
            if link.can_send and link.can_reach(address)
        ]

    async def register_hook(self, hook: MessageHook):
        # check new hook for pending messages first
        for pid in list(self.message_pool.keys()):
            package = self.message_pool.get(pid)
            if not package:
                continue

            if hook.match(package):
                await hook.put(package)
                self.message_pool.pop(pid, None)

        self.hooks.append(hook)

    async def _hook_task(self):
        self._logger.debug("Starting hook task")
        while True:
            now = datetime.utcnow()
            drop_threshold = timedelta(seconds=self.configuration.dt_hold_package_sec)
            for pid in list(self.message_pool.keys()):
                package = self.message_pool.get(pid)
                if not package:
                    continue

                if (now - package.timestamp >= drop_threshold) or await self._check_hooks(package):
                    self.message_pool.pop(pid, None)

            await trio.sleep(0.1)

    def remove_hook(self, hook: MessageHook):
        if hook in self.hooks:
            self.hooks.remove(hook)
        hook.dispose()

    async def submit_to_hooks(self, package: Package):
        """Submit incoming package to all registered hooks.  If any of the hooks matches, consumes the package then
        stop.  Otherwise, if never matched, put the package in memory channel for later re-delivery to new hooks."""
        if not await self._check_hooks(package):
            self.message_pool[package.message.hexdigest()] = package

    async def _check_hooks(self, package: Package) -> bool:
        """Check a package with each hook, send it to the ones it matches, and returns whether there was a match."""
        matched = False
        for hook in self.hooks:
            if hook.match(package):
                await hook.put(package)
                matched = True
        return matched

    async def emit_on_links(self, address: str, message: PrismMessage,
                            context: SpanContext = None, timeout_ms: int = math.inf,
                            link_filter: Callable[[Link], bool] = None,
                            ) -> bool:
        """Emit given message to address (could be a group address) on existing links.

        First, apply given filter (if any) to links found for given address.

        Then, sort all filtered links by given priority calculator (if any) into buckets/categories of the same
        priority.  If no priority function given, treat every link as the same category, so only one bucket remains.

        Finally, going through the ordered buckets of links, for each bucket try to send the given message in parallel,
        stopping when the first sending successfully returns.
        """
        if context is None:
            context = extract_span_context(message)

        if getattr(self, "local_address", None) and address == self.local_address:
            await self.local_link.send(message, context)
            return True

        links = self.links_for_address(address)
        if not links:
            if address != "*" and self.configuration.emitting_broadcast_fallback:
                self._logger.debug(f"emit_on_links: Couldn't find link for {address}, sending to all")
                address = "*"
                links = self.links_for_address(address)
            if not links:
                self._logger.debug(f"emit_on_links: Couldn't find link for {address}, giving up")
                return False

        # (1) Filter links; if given filter is None, filter() uses the identity function:
        filtered_links = list(filter(link_filter, links))

        # (2) Sort filtered links into buckets of equal priority
        # sorted_link_buckets = []

        # to cancel other send tasks when the first one was successful, use pattern from
        # https://trio.readthedocs.io/en/stable/reference-core.html#custom-supervisors
        winner = False

        async def jockey(link_to_send: Link, cancel_scope):
            nonlocal winner
            winner = await link_to_send.send(message, context, timeout_ms)
            if winner and not address.startswith("*"):  # this SEND link was successful, so stop others (only if not *)
                # self._logger.debug(f"emit: Successfully sent {str(message)} on {link} to {address}")
                cancel_scope.cancel()

        async with trio.open_nursery() as nursery:
            for link in filtered_links:
                nursery.start_soon(jockey, link, nursery.cancel_scope)

        return winner

    async def load_address(self, address: LinkAddress, endpoints: List[str], epoch: str) -> Optional[Link]:
        channels = [channel for channel in self.channels if channel.channel_id == address.channel_id]
        if not channels:
            self._logger.error(f"Could not load address (channel ID not found): {address.channel_id}")
            return None

        return await channels[0].load_link(address.link_address, endpoints, epoch)

    async def run(self):
        """Runs any background tasks that the transport needs to operate, such as polling whiteboards.
        Passes received messages to self.submit_to_hooks()"""
        await self._hook_task()
