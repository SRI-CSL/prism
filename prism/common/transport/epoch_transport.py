#  Copyright (c) 2019-2023 SRI International.

from typing import List, Optional

from prism.common.message import LinkAddress
from prism.common.transport.transport import Transport, Channel, Link, MessageHook, Package, LocalLink


class EpochMessageHook(MessageHook):
    def __init__(self, inner_hook: MessageHook, epoch: str):
        super().__init__()
        self.inner_hook = inner_hook
        self.epoch = epoch

    def match(self, package: Package) -> bool:
        if package.link and not package.link.epoch == self.epoch:
            return False

        return self.inner_hook.match(package)

    async def put(self, package: Package):
        await self.inner_hook.put(package)

    def __repr__(self):
        return f"EpochHook({self.epoch}, {self.inner_hook})"

    def dispose(self):
        super().dispose()
        self.inner_hook.dispose()


class EpochTransport(Transport):
    def __init__(self, transport: Transport, epoch: str):
        super().__init__(transport.configuration)
        self.epoch = epoch
        self._inner_transport = transport
        self._hook_map = {}
        self.local_address = transport.local_address
        self.local_link = LocalLink(self, epoch)

    @property
    def overhead_bytes(self):
        return self._inner_transport.overhead_bytes

    @property
    def channels(self) -> List[Channel]:
        return [EpochChannel(channel, self.epoch) for channel in self._inner_transport.channels]

    async def register_hook(self, hook: MessageHook):
        epoch_hook = EpochMessageHook(hook, self.epoch)
        await self._inner_transport.register_hook(epoch_hook)
        self._hook_map[id(hook)] = epoch_hook

    def remove_hook(self, hook: MessageHook):
        epoch_hook = self._hook_map[id(hook)]
        self._inner_transport.remove_hook(epoch_hook)
        del self._hook_map[id(hook)]

    async def submit_to_hooks(self, package: Package):
        await self._inner_transport.submit_to_hooks(package)

    async def load_address(self, address: LinkAddress, endpoints: List[str], epoch: str) -> Optional[Link]:
        return await self._inner_transport.load_address(address, endpoints, self.epoch)


class EpochChannel(Channel):
    def __init__(self, channel: Channel, epoch: str):
        super().__init__(channel.channel_id)
        self._inner_channel = channel
        self.epoch = epoch
        self.link_direction = channel.link_direction
        self.transmission_type = channel.transmission_type
        self.connection_type = channel.connection_type
        self.reliable = channel.reliable
        self.mtu = channel.mtu
        self.bandwidth_bps = channel.bandwidth_bps
        self.latency_ms = channel.latency_ms
        self.loss = channel.loss
        self.tags = channel.tags

    def __repr__(self):
        return repr(self._inner_channel)

    @property
    def status(self):
        return self._inner_channel.status

    @property
    def links(self) -> List[Link]:
        return [link for link in self._inner_channel.links if link.epoch == self.epoch]

    async def create_link(self, endpoints: List[str], epoch: str) -> Optional[Link]:
        return await self._inner_channel.create_link(endpoints, self.epoch)

    async def load_link(self, link_address: str, endpoints: List[str], epoch: str) -> Optional[Link]:
        return await self._inner_channel.load_link(link_address, endpoints, self.epoch)
