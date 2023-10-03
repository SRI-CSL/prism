#  Copyright (c) 2019-2023 SRI International.
from contextlib import contextmanager
from datetime import datetime
from jaeger_client import SpanContext
import logging
import math
import structlog
import time
import trio
from typing import *

from .ls_database import LSDatabase
from .ls_neighborhood import Neighborhood, Neighbor
from .ls_queue import LSQueue, QType, QItem
from prism.common.message import PrismMessage, TypeEnum, NeighborInfoMap
from prism.common.logging import MONITOR_STATUS
from prism.common.config import configuration
from prism.common.tracing import trace_context
from prism.common.util import bytes_hex_abbrv
from prism.common.state import StateStore
from prism.server.server_data import ServerData
from ...common.transport.epoch_transport import EpochTransport
from ...common.transport.transport import Transport, MessageHook, Package


class LspHook(MessageHook):

    def match(self, package: Package) -> bool:
        msg = package.message
        return msg.msg_type in {TypeEnum.LSP, TypeEnum.LSP_ACK, TypeEnum.LSP_FWD}
        # TypeEnum.LSP_DATABASE_REQUEST, TypeEnum.LSP_DATABASE_RESPONSE


class LSRouting:
    def __init__(self, server_data: ServerData, own_cost: int, transport: Transport, state_store: StateStore):
        assert server_data
        self.server_data = server_data
        self.own_pseudonym = server_data.pseudonym
        self.own_name = server_data.id
        self.own_cost = own_cost
        self._transport = transport
        self._state_store = state_store
        self.ark_in_channel: Optional[trio.MemorySendChannel] = None
        self._logger = structlog.getLogger(__name__).bind(myself=bytes_hex_abbrv(self.own_pseudonym), epoch=server_data.epoch)
        self._monitor_logger = structlog.get_logger(MONITOR_STATUS).bind(
            myself=bytes_hex_abbrv(self.own_pseudonym),
            epoch=server_data.epoch
        )

        self._own_ARK = None
        self.neighborhood = Neighborhood(self.own_name, self.own_pseudonym, transport,
                                         self.trigger_aliveness, self.remove_neighbor)

        # establish MAX values that should stay constant over runtime (TODO: Bob: answer?)
        self.ttl_max = configuration.ls_ttl_max
        self.hops_max = configuration.ls_hops_max

        # The LSP database is a map from an originator pseudonym to an LSP.
        self.LSP_DB = LSDatabase(self.create_own_LSP(), self.hops_max, server_data.epoch)

        # The Send Queue is a FIFO with (neighbor, originator) tuples.
        self.send_q: Optional[LSQueue] = None

        # The Ack Queue is a FIFO of (neighbor, originator) tuples.
        self.ack_q: Optional[LSQueue] = None

        # Linda: The Retransmission Queue is a priority queue of (neighbor, originator,
        # expiration) tuples, with the expiration being the priority, with lower
        # times having high priority.

        self.start_routing = trio.Event()  # to signal that LS routing can commence
        self._aliveness_cancel_scope = trio.CancelScope()

        self.fwd_send_ch, self.fwd_recv_ch = trio.open_memory_channel(0)

        self._logger.info(f'Link-State Routing initialized')

        saved_lsp = self._state_store.load_state("lsp")
        if saved_lsp:
            # FIXME - this code is written assuming ZCT mode and needs to be adjusted if saved LSP state might
            #         come from anywhere else
            self.LSP_DB.load_state(saved_lsp)
            self.init_neighborhood_from_cache()

    def init_neighborhood_from_cache(self):
        own_lsp = self.LSP_DB.database[self.LSP_DB.pseudonym]
        for neighbor_info in own_lsp.neighbors:
            neighbor_lsp = self.LSP_DB.database[neighbor_info.pseudonym]
            neighbor = Neighbor(address=neighbor_lsp.name, pseudonym=neighbor_lsp.originator)
            self.neighborhood.neighbors_by_pseudonym[neighbor_lsp.originator] = neighbor
        self._logger.debug(f"Initialized neighborhood: {self.neighborhood}")

    @contextmanager
    def trace_with_epoch(
            self,
            operation: str,
            parent: Optional[Union[PrismMessage, SpanContext]] = None,
            **kwargs
    ):
        tags = {**kwargs}
        if isinstance(self._transport, EpochTransport):
            tags["epoch"] = self._transport.epoch

        with trace_context(self._logger, operation, parent, **tags) as scope:
            yield scope

    @property
    def own_ARK(self) -> PrismMessage:
        return self._own_ARK

    @own_ARK.setter
    def own_ARK(self, value):
        if value and isinstance(value, PrismMessage) and value.msg_type == TypeEnum.ANNOUNCE_ROLE_KEY:
            self._own_ARK = value
            # only trigger new LSP generation if old ARK had expired or originated a while ago
            self._aliveness_cancel_scope.cancel()
        else:
            self._own_ARK = None

    def trigger_aliveness(self):
        self._aliveness_cancel_scope.cancel()

    async def resolve_address(self, message: PrismMessage, context: SpanContext) -> Tuple[str, PrismMessage]:
        if message.pseudonym is None:
            self._logger.error(f"Asked to resolve address for message with empty pseudonym: {message}")
            return "*", message

        destination = await self.next_hop_for(message.pseudonym.hex())
        if destination is not None:
            # we need to forward this message via an intermediate hop:
            next_hop_pseudonym = bytes.fromhex(destination)
            address = self.neighborhood.get_address_for(next_hop_pseudonym)
            if address is None:
                with self.trace_with_epoch('lsp-cannot-resolve', context,
                                           next_hop=destination[:6],
                                           destination=bytes_hex_abbrv(message.pseudonym)) as scope:
                    scope.warning(f"Cannot resolve address for next hop destination={destination[:6]} " +
                                  "- falling back to anonymous broadcast")
                return "*", message
            with self.trace_with_epoch('lsp-next-hop', context,
                                       next_hop=destination[:6], next_hop_address=address,
                                       destination=bytes_hex_abbrv(message.pseudonym)) as scope:
                scope.debug(f"Calculated next hop as {address}", next_hop=destination[:6])
            return address, PrismMessage(msg_type=TypeEnum.LSP_FWD,
                                         pseudonym=next_hop_pseudonym,
                                         from_neighbor=self.own_pseudonym,
                                         sub_msg=message)

        # try to resolve address from local table:
        address = self.neighborhood.get_address_for(message.pseudonym)
        if address is None:
            self._logger.debug(f"Failed to resolve address from local table for {message.pseudonym.hex()[:6]}")
            return "*", message
        return address, message

    def create_own_LSP(self) -> PrismMessage:
        return PrismMessage(msg_type=TypeEnum.LSP,
                            originator=self.own_pseudonym,
                            micro_timestamp=int(time.time() * 1e6),
                            ttl=configuration.ls_time_to_live,
                            neighbors=[NeighborInfoMap(pseudonym=n, cost=self.own_cost)
                                       for n in self.neighborhood.other_neighbors()],
                            sub_msg=self.own_ARK,
                            hop_count=0,
                            sender=self.own_pseudonym)

    async def emit_ls_msg(self, address: str, message: PrismMessage, context: SpanContext = None) -> bool:
        # self._logger.debug(f"emit_unicast: {message.msg_type} to {address}", msg=str(message))
        # TODO: Linda: only use links of established Neighbor channel!
        success = await self._transport.emit_on_links(address, message, context, link_filter=Neighborhood.link_filter)
        if not success:
            await self.neighborhood.presume_dead(address)
        return success

    async def emitting_loop(self, receive_channel: trio.MemoryReceiveChannel):
        async with receive_channel:
            async for qtype, neighbor, originator in receive_channel:
                neighbor_name = self.neighborhood.get_address_for(neighbor)
                if neighbor_name is None:
                    self._logger.debug(f'Received a Queue item for an unknown neighbor - skipping!',
                                       neighbor=bytes_hex_abbrv(neighbor))
                    continue
                # 1) get current LSP for originator
                lsp = await self.LSP_DB.lookup(originator)
                if lsp is None:
                    self._logger.warning(f'No LSP for given originator {bytes_hex_abbrv(originator)} known',
                                         neighbor=bytes_hex_abbrv(neighbor), originator=bytes_hex_abbrv(originator))
                    continue
                if qtype == QType.SEND:
                    # 2) TODO: add retransmission timer for (neighbor, originator, now + retransmission interval)
                    #     to the Timer Queue
                    # 3) send LSP to neighbor
                    await self.emit_ls_msg(neighbor_name, lsp)
                elif qtype == QType.ACK:
                    # 2) send LSP-ACK for originator and the LSP’s timestamp value to neighbor
                    lsp_ack = PrismMessage(msg_type=TypeEnum.LSP_ACK,
                                           from_neighbor=self.own_pseudonym,
                                           sender=lsp.sender,
                                           originator=lsp.originator,
                                           micro_timestamp=lsp.micro_timestamp)
                    await self.emit_ls_msg(neighbor_name, lsp_ack)
                else:
                    self._logger.warning(f'Cannot emit based on Q type {qtype}')

    async def forward_msg(self, submessage: PrismMessage, context: SpanContext):
        for n_try in range(1, configuration.ls_n_tries_fowarding + 1):
            with self.trace_with_epoch('lsp-forward', context, sub_msg_type=f'{submessage.msg_type}') as scope:
                # passing the hot potato:
                address, message = await self.resolve_address(submessage, scope.context)
                scope.info(f"LSP forwarding to {address} for pseudonym {bytes_hex_abbrv(submessage.pseudonym)}")
            # TODO: FIXME avoid "*" resolution if cannot resolve
            if address != "*" and await self.emit_ls_msg(address, message, context):
                break
            self._logger.debug(f"LSP Forwarding to {address} didn't work at the {n_try}. try - " +
                               f"sleeping for {configuration.ls_sleep_try_forwarding}s")
            await trio.sleep(configuration.ls_sleep_try_forwarding)

    async def forwarding_loop(self):
        self._logger.info(f"Starting forwarding loop")
        async with trio.open_nursery() as nursery:
            async with self.fwd_recv_ch:
                async for submessage, context in self.fwd_recv_ch:
                    nursery.start_soon(self.forward_msg, submessage, context)

    def log_human_routing_table(self, table: Dict[str, str], where: str, has_changed: bool = True,
                                level: int = logging.INFO):
        human_routing_table = {
            f"{target[:6]} ({self.neighborhood.get_address_for(bytes.fromhex(target))})":
                f"{hop[:6]} ({self.neighborhood.get_address_for(bytes.fromhex(hop))})"
            for target, hop in table.items()}
        if has_changed:  # only print in human-readable log if changed
            self._logger.log(level, f'Current routing table of length={len(table)} ({where}): ' +
                             f'{human_routing_table if len(table) < 25 else "{...}"}',
                             size=len(table))
        self._monitor_logger.info(f'Current routing table', func_name=where, table=human_routing_table)

    async def aliveness_loop(self):
        await self.LSP_DB.main_loop_started.wait()  # make sure all shared resources are initialized
        self._logger.debug(f'Starting aliveness loop')
        while True:
            # 1) update myself
            own_lsp = self.create_own_LSP()
            updated, _ = await self.LSP_DB.update_if(own_lsp)
            assert updated  # a fresh LSP should always update
            # self._logger.debug('new LSP generated', ark=str(own_lsp.sub_msg))
            # 2) for every neighbor, add (neighbor, me) to the LSP send queue
            for neighbor in [nim.pseudonym for nim in own_lsp.neighbors]:
                item = QItem(neighbor, self.own_pseudonym)
                # self._logger.debug(f"Q'ing myself to neighbor {bytes_hex_abbrv(neighbor)} " +
                #                    f"({self.name_by_pseudonym.get(neighbor)})", item=str(item))
                await self.send_q.insert_item(item)
            # 3) trigger routing table update task
            current_routing_table, has_changed = await self.LSP_DB.update_routing_table()
            self.log_human_routing_table(current_routing_table, 'aliveness', has_changed)
            # 4) sleep for significantly less than TTL, to refresh myself before expiry
            with trio.move_on_after(configuration.ls_own_refresh * own_lsp.ttl) as self._aliveness_cancel_scope:
                await trio.sleep_forever()
            if self._aliveness_cancel_scope.cancel_called:
                self._logger.debug(f'interrupted my beauty sleep to deal with new LSP (ARK or changed neighbors...)',
                                   remaining_sleep=self._aliveness_cancel_scope.deadline - trio.current_time())

    async def lsp_listen_loop(self):
        self._logger.debug(f'Starting LSP listen loop')
        lsp_hook = LspHook()
        await self._transport.register_hook(lsp_hook)
        while True:
            package = await lsp_hook.receive_pkg()
            await self.handle_msg(package.message, package.context)

    async def remove_neighbor(self, pseudonym: bytes):
        if pseudonym == self.own_pseudonym:
            self._logger.warning(f"Attempting to remove myself - shouldn't happen so ignoring!")
            return
        # 1) Remove LSP for neighbor
        await self.LSP_DB.remove_from_db(pseudonym)
        # 2) Remove any entries for neighbor in send queue, ack queue, and TODO: Linda: retransmission Q
        await self.send_q.remove_item_for_neighbor(pseudonym)
        await self.ack_q.remove_item_for_neighbor(pseudonym)

    async def handle_msg(self, message: PrismMessage, context: SpanContext):

        if message.msg_type == TypeEnum.LSP:
            # When an LSP is received it is first validated.  If signed, the
            # signature is checked.  If "timestamp" is more than 30 seconds in the
            # future, or if its originator is the receiving node, it is ignored.  If
            # the "ttl" is bigger than the largest allowed TTL, it is set to the
            # largest allowed TTL.  The LSP sender is set to the receiver, and the
            # hop count is incremented.
            micro_thirty_secs_future = int((time.time() + 30) * 1e6)
            if message.originator == self.own_pseudonym or message.micro_timestamp > micro_thirty_secs_future:
                # self._logger.debug(f'Received LSP ignored', originator=bytes_hex_abbrv(message.originator))
                return
            validated_lsp = message.clone(ttl=max(min(message.ttl, self.ttl_max), 0),  # TTL stays in [0; TTL_MAX]
                                          sender=self.own_pseudonym,
                                          hop_count=message.hop_count + 1)
            assert set(message.neighbors) == set(validated_lsp.neighbors)
            # If the LSP validates and the "timestamp" field
            # is more recent, then this update takes precedence over the prior value
            # and the database is updated and the update process is triggered.
            # If the existing database entry has the same timestamp and neighbors, a hop
            # count of HOPS_MAX, and the LSP has a hop count less than HOPS_MAX - 1,
            # then the database is updated and the update process is triggered.
            updated, new_arks = await self.LSP_DB.update_if(validated_lsp, original_digest=message.hexdigest())

            # If the hop count is less than or equal to the maximum hop count, then a
            # (neighbor, originator) tuple is added to the send queue for all
            # neighbors other than the neighbor that sent the LSP, and any
            # (neighbor, originator) retransmission timer is removed.
            if updated and validated_lsp.hop_count < self.hops_max:
                for neighbor in self.neighborhood.other_neighbors() - {message.sender}:
                    await self.send_q.insert_item(QItem(neighbor, message.originator))
                    # TODO: clear (neighbor, validated_lsp.originator) retransmission timer, if it exists
            if updated:
                current_routing_table, has_changed = await self.LSP_DB.update_routing_table()
                self.log_human_routing_table(current_routing_table, 'handle_msg', has_changed)

            # A (sender, originator) tuple is added to the ACK queue for this LSP.
            await self.ack_q.insert_item(QItem(message.sender, message.originator))

            # add new_arks (really just a list of one at max) to announcing role's ark_store:
            if self.ark_in_channel:
                for ark_message in new_arks:
                    await self.ark_in_channel.send(Package(ark_message, context, datetime.utcnow()))

            await self.neighborhood.set_alive(message.originator)

        if message.msg_type == TypeEnum.LSP_ACK:
            # When an LSP-ACK is received with a timestamp greater than or equal to the
            # timestamp of the originator's LSP in the LSP database, the ACKing
            # (neighbor, originator) is removed from the retransmission queue.
            originator_lsp = await self.LSP_DB.lookup(message.originator)
            if originator_lsp and message.micro_timestamp >= originator_lsp.micro_timestamp:
                pass  # TODO: remove (message.from_neighbor, message.originator) from retransmission Q;
                #        ask Bob if from_neighbor is correct and not sender!

            await self.neighborhood.set_alive(message.from_neighbor)

        if message.msg_type == TypeEnum.LSP_FWD:
            # We also handle the forwarding of wrapped and routed messages here:
            submessage = PrismMessage.from_cbor_dict(message.sub_msg.as_cbor_dict())
            if submessage.pseudonym == self.own_pseudonym:  # reached destination
                # self._logger.debug(f'Found forwarded message {submessage.msg_type} for myself')
                await self._transport.local_link.send(submessage, context)
            else:  # more forwarding needed:
                await self.fwd_send_ch.send((submessage, context))

            await self.neighborhood.set_alive(message.from_neighbor)

        # TODO: Database_Request & _Response

    async def next_hop_for(self, destination: str) -> Optional[str]:
        """
        Look up next hop for destination if routing table has an entry.
        Return None if no information is known in the routing table or if the next hop would be the same as destination.
        """
        next_hop = await self.LSP_DB.next_hop(destination)
        return None if next_hop == destination else next_hop

    async def main_task(self):
        await self.start_routing.wait()
        self._logger.info(f'Link-State Routing started')

        async with trio.open_nursery() as nursery:
            nursery.start_soon(self.forwarding_loop)
            nursery.start_soon(self.lsp_listen_loop)

            if configuration.control_traffic:
                nursery.start_soon(self.aliveness_loop)
                nursery.start_soon(self.LSP_DB.main_loop)
                nursery.start_soon(self.neighborhood.main_task)
                send_channel, receive_channel = trio.open_memory_channel(math.inf)
                async with send_channel, receive_channel:
                    self.send_q = LSQueue(QType.SEND, send_channel.clone())
                    self.ack_q = LSQueue(QType.ACK, send_channel.clone())
                    nursery.start_soon(self.send_q.rate_limited_processing)
                    nursery.start_soon(self.ack_q.rate_limited_processing)
                    # TODO: retransmission Q...
                    nursery.start_soon(self.emitting_loop, receive_channel.clone())
