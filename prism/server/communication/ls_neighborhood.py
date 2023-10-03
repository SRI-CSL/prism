#  Copyright (c) 2019-2023 SRI International.
from dataclasses import dataclass, field
import math
import structlog
import trio
from typing import Set, Optional, Callable, Dict, List, Awaitable, Union, Tuple

from prism.common.transport import transport as dt
from prism.common.message import TypeEnum, PrismMessage
from prism.common.config import configuration
from prism.common.transport.enums import ConnectionType, TransmissionType
from prism.common.util import bytes_hex_abbrv


@dataclass
class Neighbor:
    address: str
    pseudonym: bytes
    channel_gid: str = field(default=None)  # my own entry does not contain a link

    def __repr__(self):
        return f"Neighbor<{self.address},{bytes_hex_abbrv(self.pseudonym)},{self.channel_gid}"


class NhHook(dt.MessageHook):

    def match(self, package: dt.Package) -> bool:
        return package.message.msg_type in {TypeEnum.LSP_HELLO, TypeEnum.LSP_HELLO_RESPONSE}


class Neighborhood:

    def __init__(self, own_address: str, own_pseudonym: bytes, transport: dt.Transport,
                 aliveness: Callable[[], None], remove_neighbor: Callable[[bytes], Awaitable[None]]):
        self.myself = Neighbor(own_address, own_pseudonym)
        self._transport = transport
        self.trigger_aliveness = aliveness
        self.remove_neighbor = remove_neighbor

        self.neighbors_by_pseudonym = {self.myself.pseudonym: self.myself}  # established neighborhood
        self.timers_send_channel, self.timers_receive_channel = trio.open_memory_channel(math.inf)
        self.timers = {}  # type: Dict[bytes, trio.CancelScope]
        self.attempts_remaining = {}  # type: Dict[Tuple[str, str], int]

        self._logger = structlog.getLogger(__name__).bind(own_address=own_address,
                                                          own_pseudonym=bytes_hex_abbrv(own_pseudonym))

    def __repr__(self):
        neighbors_str = ", ".join(f"{bytes_hex_abbrv(p)} -> {n}" for p, n in self.neighbors_by_pseudonym.items())
        return f"Neighborhood({neighbors_str})"

    # API --- begin ---
    def get_address_for(self, pseudonym: bytes) -> Optional[str]:
        n = self.neighbors_by_pseudonym.get(pseudonym)
        return None if n is None else n.address

    def get_neighbors_for(self, address: str) -> List[Neighbor]:
        return [n for n in self.neighbors_by_pseudonym.values() if n.address == address]

    async def set_alive(self, pseudonym: bytes):
        """Remove any presumed dead timer, and start or reset ALIVE timer for given pseudonym."""
        if pseudonym == self.myself.pseudonym:
            return  # skip myself
        neighbor = self.neighbors_by_pseudonym.get(pseudonym)
        if neighbor is not None:
            await self.timers_send_channel.send((neighbor, True))
        else:
            pass  # ignore messages originating from non-neighbors

    def is_alive(self, neighbor: Union[str, bytes]) -> bool:
        if type(neighbor) is str:
            return neighbor in self.other_neighbors_addresses()
        if type(neighbor) is bytes:
            return neighbor in self.neighbors_by_pseudonym
        return False

    async def declare_dead(self, address: str) -> bool:
        """
        For all neighbors matching given address (and not referring to myself):
         - remove from current neighborhood
         - stop and remove timers
         - TODO: ask for new link to be created on same channel as before?  Or on any suitable channel??
         If any neighbors matched, then trigger aliveness loop and return True.
        """
        dead_neighbors = [n for n in self.get_neighbors_for(address) if n.pseudonym != self.myself.pseudonym]
        for neighbor in dead_neighbors:
            self._logger.warning(f"declare neighbor dead: {neighbor}")
            self.cancel_and_remove_timer(neighbor.pseudonym)
            dead_neighbor = self.neighbors_by_pseudonym.pop(neighbor.pseudonym, None)
            # clear log of attempts, if any
            self.attempts_remaining.pop((neighbor.address, neighbor.channel_gid), None)
            await self.remove_neighbor(neighbor.pseudonym)
            # TODO: try to create a new link to lost neighbor (TODO: on other channels???):
            if dead_neighbor:
                for ch in self._transport.channels:
                    if Neighborhood.is_suitable_channel(ch):
                        self._logger.debug(f"TODO: Asking for new link to {address}", channel=ch)
                        # new_link = await ch.create_link([address])
                        # if self.suitable_receiver(new_link) == dead_neighbor.address:
                        #     # TODO: Success!
                        #     self._logger.info(f"Got new link: {new_link}")  # could be None!  Or useless RECV link...
        if len(dead_neighbors) > 0:
            self.trigger_aliveness()
            return True
        return False  # no one ALIVE matched

    async def presume_dead(self, address: str):
        neighbors = [n for n in self.get_neighbors_for(address) if n.pseudonym != self.myself.pseudonym]
        for neighbor in neighbors:
            await self.timers_send_channel.send((neighbor, False))

    def other_neighbors(self) -> Set[bytes]:
        return set(self.neighbors_by_pseudonym.keys()) - {self.myself.pseudonym}

    def other_neighbors_addresses(self) -> Set[str]:
        return {n.address for n in self.neighbors_by_pseudonym.values() if n.address != self.myself.address}
    # API --- end ---

    @staticmethod
    def is_suitable_channel(ch: dt.Channel) -> bool:
        if ch is None:
            return False
        return ch.connection_type != ConnectionType.INDIRECT

    @staticmethod
    def link_filter(link: dt.Link) -> bool:
        return link.link_type.can_send \
               and link.connection_status.usable \
               and link.channel.connection_type != ConnectionType.INDIRECT \
               and link.channel.transmission_type == TransmissionType.UNICAST

    @staticmethod
    def suitable_receiver(link: dt.Link) -> Optional[str]:
        if link is None:
            return None
        if not Neighborhood.is_suitable_channel(link.channel):
            return None  # skip links for this channel
        # only consider SEND|BIDI links with exactly 1 endpoint that matches "*-server-XXX"
        if Neighborhood.link_filter(link):
            return link.endpoints[0]
        return None

    def cancel_and_remove_timer(self, pseudonym: bytes):
        timer_scope = self.timers.pop(pseudonym, trio.CancelScope())
        timer_scope.cancel()

    async def alive_timer(self, timeout: float, pseudonym: bytes, scope: trio.CancelScope):
        with scope:
            await trio.sleep(timeout)
            neighbor = self.neighbors_by_pseudonym.get(pseudonym, None)
            if neighbor is not None:  # neighbor with this pseudonym still exists
                # self._logger.debug(f"ALIVE timer for {neighbor.address} expired; demoting to PRESUMED DEAD",
                #                    neighbor=str(neighbor), timeout=f"{timeout%.2}")
                await self.say_hello(neighbor.address, neighbor.channel_gid)
                await self.timers_send_channel.send((neighbor, False))

    async def presumed_dead_timer(self, timeout: float, address: str, scope: trio.CancelScope):
        with scope:
            await trio.sleep(timeout)
            if await self.declare_dead(address):
                self._logger.warning(f"Address {address} has not received sign of life  within {timeout:.2f}s")

    async def start_timers(self):
        self._logger.debug(f'Starting LS neighborhood task to restart ALIVE and PRESUMED DEAD timers')
        async with trio.open_nursery() as nursery:
            async with self.timers_receive_channel:
                async for neighbor, is_alive in self.timers_receive_channel:
                    assert neighbor
                    # cancel any active timer before starting a new one:
                    self.cancel_and_remove_timer(neighbor.pseudonym)
                    scope = trio.CancelScope()
                    self.timers[neighbor.pseudonym] = scope
                    if is_alive:
                        nursery.start_soon(self.alive_timer,
                                           configuration.ls_alive_factor * configuration.cs2_ark_timeout * 60,
                                           neighbor.pseudonym,
                                           scope)
                    else:
                        # self._logger.debug(f'Starting PRESUMED DEAD timer for {neighbor.address}', neighbor=neighbor)
                        nursery.start_soon(self.presumed_dead_timer,
                                           configuration.ls_presumed_dead_timeout,
                                           neighbor.address,
                                           scope)

    async def listen_loop(self):
        self._logger.debug(f'Starting LS neighborhood listen loop')
        msg_hook = NhHook()
        await self._transport.register_hook(msg_hook)
        async with trio.open_nursery() as nursery:
            while True:
                package = await msg_hook.receive_pkg()
                nursery.start_soon(self.handle_msg, package.message)

    async def handle_msg(self, message: PrismMessage):
        # self._logger.debug(f"handle_msg: {str(message)}")

        if message.msg_type == TypeEnum.LSP_HELLO and message.from_neighbor != self.myself.pseudonym:
            # reset any blocked HELLO attempts for (message.name, *):
            # NOTE: this assumes that direct, server-to-server links are generally functional in both directions, i.e.,
            #       we heard from (potential) neighbor and should be able to get an LSP Hello through in the near future
            for (address, channel_gid), attempts in self.attempts_remaining.copy().items():
                if address == message.name and attempts <= 0:
                    self._logger.debug(f"resetting LSP HELLO attempts for ({message.name}, {channel_gid})")
                    self.attempts_remaining.pop((address, channel_gid))
            # always reply on any suitable link:
            if not await self._transport.emit_on_links(
                    message.name,
                    PrismMessage(msg_type=TypeEnum.LSP_HELLO_RESPONSE,
                                 from_neighbor=self.myself.pseudonym,
                                 to_neighbor=message.from_neighbor,
                                 name=self.myself.address,
                                 whiteboard_ID=message.whiteboard_ID),  # abusing this unused field...
                    timeout_ms=configuration.ls_neighbor_timeout_ms,
                    link_filter=(lambda l: Neighborhood.suitable_receiver(l) == message.name)):
                self._logger.warning(f'Cannot reply to LSP Hello from {message.name} with response; PRESUMED DEAD')
                await self.presume_dead(message.name)
            else:
                # self._logger.debug(f"replied to LSP HELLO from ({message.name}, {message.whiteboard_ID})")
                await self.set_alive(message.from_neighbor)

        if message.msg_type == TypeEnum.LSP_HELLO_RESPONSE:
            # self._logger.debug(f"Received LSP Hello Response from {message.name} with {message.whiteboard_ID}",
            #                    msg=str(message))
            if message.to_neighbor == self.myself.pseudonym and message.from_neighbor not in self.other_neighbors():
                new_neighbor = Neighbor(message.name, message.from_neighbor, channel_gid=message.whiteboard_ID)
                self._logger.info(f"New neighbor discovered: {new_neighbor}")
                self._logger.debug(f"received first LSP HELLO RESPONSE from {message.name}",
                                   channel_gid=message.whiteboard_ID)
                self.neighbors_by_pseudonym[message.from_neighbor] = new_neighbor
                # clear log of attempts, if any:
                self.attempts_remaining.pop((message.name, message.whiteboard_ID), None)
                self.trigger_aliveness()
            await self.set_alive(message.from_neighbor)

    async def say_hello(self, neighbor_address: str, channel_gid: str) -> bool:
        return await self._transport.emit_on_links(
            neighbor_address,
            PrismMessage(msg_type=TypeEnum.LSP_HELLO,
                         from_neighbor=self.myself.pseudonym,
                         name=self.myself.address,
                         whiteboard_ID=channel_gid),  # abusing this unused field...
            timeout_ms=configuration.ls_neighbor_timeout_ms,
            link_filter=(lambda l: l.channel.channel_id == channel_gid))

    async def discover_neighbors(self):
        self._logger.debug(f'Starting LS neighborhood discovery loop')
        # in regular intervals "ls_neighbor_discovery_sleep", collect current neighbor addresses and then go through all
        # current suitable links to potential (not registered) neighbors:
        # - send LSP Hello to potential neighbor address on link ID

        # before sleeping and looping again, also declare any unprocessed current neighbors dead
        while True:
            # collect potential new and current neighbors
            current_neighbors = self.other_neighbors_addresses()
            for ch in self._transport.channels:
                for link in ch.links:
                    potential_neighbor = Neighborhood.suitable_receiver(link)
                    if potential_neighbor is not None \
                            and potential_neighbor != self.myself.address \
                            and potential_neighbor not in current_neighbors:
                        # check number of attempts first
                        attempts = self.attempts_remaining.get(
                            (potential_neighbor, link.channel.channel_id),
                            configuration.ls_max_discovery_attempts
                            if configuration.ls_max_discovery_attempts
                            else math.inf)
                        if attempts <= 0:
                            continue  # no longer say hello to this potential neighbor on this link
                        self.attempts_remaining[(potential_neighbor, link.channel.channel_id)] = attempts - 1
                        self._logger.debug(f"say LSP HELLO to {potential_neighbor}; remaining attempts = {attempts}",
                                           channel_gid=link.channel.channel_id)
                        # TODO: spawn into its own task!?
                        await self.say_hello(potential_neighbor, link.channel.channel_id)
            await trio.sleep(configuration.ls_neighbor_discovery_sleep)

    async def main_task(self):
        self._logger.info(f'Link-State Neighborhood management started')
        async with trio.open_nursery() as nursery:
            nursery.start_soon(self.discover_neighbors)
            nursery.start_soon(self.listen_loop)
            nursery.start_soon(self.start_timers)
