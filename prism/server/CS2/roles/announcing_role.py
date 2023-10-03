#  Copyright (c) 2019-2023 SRI International.
from abc import ABCMeta
from datetime import datetime, timedelta
from jaeger_client import SpanContext
import math
from random import Random
from time import time
import trio
from typing import Set, Tuple, List, Optional

from prism.common.crypto.verify import verify_ARK, sign_ARK
from prism.common.message import create_ARK, TypeEnum, PrismMessage
from prism.common.transport.transport import MessageHook, Package, Link
from prism.common.util import frequency_limit
from prism.common.vrf.link import is_link_compatible
from prism.common.vrf.sortition import VRFSortition
from prism.server.communication.logical_link import LogicalLink
from ...CS2.ark_store import ArkStore
from ...CS2.roles.abstract_role import AbstractRole
from prism.common.config import configuration
from ...pki import ServerPKI


class ArkHook(MessageHook):
    def __init__(self, server_data):
        super().__init__()
        self.server_data = server_data

    def match(self, package: Package) -> bool:
        msg = package.message
        # don't verify ARK here as we want to consume it even if it doesn't pass verification
        return msg.msg_type == TypeEnum.ANNOUNCE_ROLE_KEY and self.server_data.pseudonym != msg.pseudonym


class AnnouncingRole(AbstractRole, metaclass=ABCMeta):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        assert self.server_data

        self._ark_hook = ArkHook(self.server_data)
        self.ark_store = ArkStore(self._state_store, self.epoch)
        self.handoff_store: Optional[ArkStore] = None
        self._last_known = set()
        self.ls_routing.ark_in_channel = self._ark_hook.in_channel
        self.ls_routing.LSP_DB.trigger_nark = self.trigger_nark_loop
        self.nark_scope = trio.CancelScope()
        self.incoming_links = []
        self.outgoing_links = []
        self.logical_links = {}
        self.vrf_sortition: Optional[VRFSortition] = None

    def ark_data(self) -> dict:
        # can be overridden to add more parameters as needed by specific roles
        d = self.server_data.ark_data()

        if self.incoming_links:
            d["link_addresses"] = [link.address_cbor for link in self.incoming_links]

        if self.outgoing_links:
            d["broadcast_addresses"] = [link.address_cbor for link in self.outgoing_links]

        return d

    @property
    def ark_ready(self) -> bool:
        return True

    @property
    def ark_broadcasting(self) -> bool:
        return True

    def monitor_data(self) -> dict:
        return {
            "valid_ark_count": len(self.ark_store.valid_servers),
            "arking": self.ark_ready,
            **super().monitor_data()
        }

    async def ark_update_loop(self):
        self._logger.debug(f'Starting ARK update loop')
        if configuration.get("ls_routing", False):
            self.ls_routing.start_routing.set()

        last_ark_data = None
        last_update_time = datetime.min

        while True:
            if not self.ark_ready:
                await trio.sleep(1)
                continue

            ark_data = self.ark_data()
            if not ark_data:
                await trio.sleep(1)
                continue

            ark_interval = timedelta(seconds=max(math.ceil(configuration.cs2_ark_timeout * 60), 0))

            if ark_data == last_ark_data and datetime.utcnow() - last_update_time < ark_interval:
                await trio.sleep(1)
                continue

            last_ark_data = ark_data
            last_update_time = datetime.utcnow()

            expiration_factor = max(configuration.get('cs2_ark_expiration_factor', 1.0), 1)
            expiration = time() + ark_interval.total_seconds() * expiration_factor
            message = create_ARK(expiration=int(expiration), micro_timestamp=int(time() * 1e6), **ark_data)
            signed_ark = sign_ARK(message, self.server_key)

            self._logger.debug(f"Updated own ARK: {str(signed_ark)}")

            self.ark_store.record(signed_ark, True)
            self.update_known()

            # are we using LS Routing?  Then update my own ARK to be sent embedded in LSP messages.
            if self.ls_routing.start_routing.is_set():
                self.ls_routing.own_ARK = signed_ark
            else:
                # Otherwise, send to (anonymous) broadcast
                await self.emit(signed_ark, "*")

            await trio.sleep(1)

    async def ark_broadcast_loop(self):
        """In this task, we broadcast known ARKs to connected clients (using *client address) at a fixed rate
        prioritizing the ARKs we've broadcast least recently. Whenever our own ARK changes, we backdate its
        last broadcast to the beginning of time to put it at the head of the queue.

        Sub-classing roles can choose to turn off the emitting of ARKS if they set `ark_broadcasting` to False.
        """
        await self.ls_routing.start_routing.wait()  # don't broadcast ARKS until we have LS Routing enabled
        self._logger.debug(f'Starting ARK broadcast loop')
        while True:
            await trio.sleep(configuration.cs2_ark_sleep_time)
            self.update_known()

            if not self.ark_ready or not self.ark_broadcasting:
                continue

            # In the handoff phase between epochs, start broadcasting ARKs from the new epoch
            if self.handoff_store:
                self._logger.debug("Broadcasting ARKs from next epoch")
                broadcast_store = self.handoff_store
            else:
                broadcast_store = self.ark_store

            ark_links = self._transport.links_for_address("*client") + self.outgoing_links
            if not ark_links:
                self._logger.warning("No links to broadcast ARKs on.")
                continue

            ark_mtu = self.ark_mtu(ark_links)
            arks_message = broadcast_store.broadcast_message(self.server_data, mtu=ark_mtu)
            if not arks_message:
                self._logger.warning("No ARKs to broadcast.")
                continue

            ark_count = len(arks_message.submessages)
            with self.trace("ark-broadcast", ark_count=ark_count, ark_mtu=ark_mtu) as scope:
                scope.debug(f"Broadcasting {ark_count} ARKs")
                await self.broadcast(arks_message, context=scope.context)

    # TODO - use for dropbox replies as well?
    async def broadcast(self, message: PrismMessage, context: SpanContext):
        broadcast_links = self._transport.links_for_address("*client") + self.outgoing_links
        message_size = len(message.encode())
        for link_number, link in enumerate(broadcast_links):
            with self.trace(
                    "broadcast",
                    context,
                    link_number=link_number + 1,
                    link_count=len(broadcast_links),
                    message_size=message_size,
            ) as scope:
                await link.send(message, context=scope.context, timeout_ms=configuration.emit_ark_timeout_ms)
                scope.debug(f"Sent {message.msg_type} ({message_size}B) to "
                            f"client ({link_number + 1}/{len(broadcast_links)}).")
                # Sleep between broadcasts in a batch
                if link_number + 1 != len(broadcast_links):
                    await trio.sleep(configuration.cs2_ark_sleep_time)

    def ark_mtu(self, ark_links: List[Link]) -> int:
        mtu = configuration.cs2_arks_max_mtu
        for link in ark_links:
            if link.channel.mtu is not None and link.channel.mtu > 0:
                mtu = min(mtu, link.channel.mtu)
        return mtu - self._transport.overhead_bytes

    def handoff_arks(self, new_ark_store: ArkStore):
        self.handoff_store = new_ark_store

    async def _calc_reachability(self, previously: Set[str]) -> Tuple[Set[str], Set[str], Set[str]]:
        currently = await self.ls_routing.LSP_DB.reachable_destinations()
        return currently - previously, previously - currently, currently

    def trigger_nark_loop(self):
        self.nark_scope.cancel()

    async def nark_broadcast_loop(self):
        """
        Tracks which servers have had NARKs broadcast
        Checks to see if any servers that weren't reachable are now reachable and vice versa.
          If yes, go to 3. If no, go to 7.
        Pauses for nark_confirmation_seconds seconds
        Runs the checks again
        For any servers that were newly reachable in both checks, put their ARKs near the top of the queue by
          setting last_broadcast to datetime.min + 1 second
        For any servers that were newly unreachable in both checks, add them to the NARK list and broadcast a NARK
          message with a list of unreachable servers
        sleep for nark_timeout_seconds
        """
        self._logger.debug(f'Starting NARK broadcast loop')
        previously_reachable = set()
        while True:
            if not configuration.nark or not self.ark_broadcasting:
                await trio.sleep(1.0)
                continue

            # first check:
            newly_reachable1, no_longer_reachable1, previously_reachable1 = \
                await self._calc_reachability(previously_reachable)
            if len(newly_reachable1) or len(no_longer_reachable1):
                await trio.sleep(configuration.nark_confirmation_seconds)
                # confirmation check:
                newly_reachable2, no_longer_reachable2, _ = \
                    await self._calc_reachability(previously_reachable)
                for new_server in newly_reachable1 & newly_reachable2:
                    self.ark_store.promote(bytes.fromhex(new_server))
                no_longer_reachable = no_longer_reachable1 & no_longer_reachable2
                if len(no_longer_reachable):
                    # update ARK store accordingly:
                    for pseudonym_hex in no_longer_reachable:
                        self.ark_store.remove(bytes.fromhex(pseudonym_hex))

                    with self.trace("nark_broadcast", n_unreachable=len(no_longer_reachable)) as scope:
                        message = PrismMessage(msg_type=TypeEnum.NARK,
                                               pseudonym=self.pseudonym,
                                               micro_timestamp=int(time() * 1e6),
                                               dead_servers=[bytes.fromhex(n) for n in no_longer_reachable])
                        scope.debug(f"Sending NARK for {len(no_longer_reachable)} no longer reachable servers")
                        await self.broadcast(message, context=scope.context)
            previously_reachable = previously_reachable1
            with trio.move_on_after(configuration.nark_timeout_seconds) as self.nark_scope:
                await trio.sleep_forever()

    def update_known(self, parent_span_context: SpanContext = None):
        currently_known = self.ark_store.valid_servers
        current_set = {rec.pseudonym for rec in currently_known}
        known_str = ', '.join(f'{str(rec)}' for rec in currently_known)
        self._monitor_logger.info('update known servers', size=len(currently_known), known_servers=currently_known)
        if len(current_set.symmetric_difference(self._last_known)) > 0:
            with self.trace("currently-known-servers", parent_span_context, currently_known=len(currently_known)) \
                    as scope:
                scope.info(f'currently known servers ({len(currently_known)})' +
                           (f': [{known_str}]' if len(currently_known) < configuration.get("log_max_known", 6) else ''),
                           known_server_count=len(currently_known))
        self._last_known = current_set

    async def ark_listen_loop(self):
        self._logger.debug(f'Starting ARK listen loop')
        await self._transport.register_hook(self._ark_hook)
        while True:
            package = await self._ark_hook.receive_pkg()
            message = package.message
            if verify_ARK(message, self.vrf_sortition, self.root_certificate):
                self.ark_store.record(message)
                self.update_known(parent_span_context=package.context)
            else:
                self._logger.warning(f"Could not verify ARK {str(message)}")

    def link_targets(self, seed: int) -> List[Tuple[PrismMessage, str]]:
        """
        Returns a list of PrismMessages that contain pseudonym and link address information.
        By default, everybody wants to link to 3 compatible EMIXes.
        Override in subclasses to expand/replace link candidates.
        """

        probability = configuration.get("vrf_outer_link_probability")
        emixes = [server for server in self.previous_role.flooding.payloads
                  if server.role == "EMIX" and
                  is_link_compatible(self.pseudonym, server.pseudonym, probability)]
        Random(seed).shuffle(emixes)
        return [(emix, "lsp") for emix in emixes[:configuration.get("other_server_emix_links", 3)]]

    async def link_maintenance_loop(self):
        # Fixed random seed for stable sort
        seed = Random().randint(1, 2**64)
        async with trio.open_nursery() as nursery:
            while True:
                link_targets = self.link_targets(seed)

                if frequency_limit(f"link-target-selection-{self.epoch}"):
                    target_names = [eark.name for eark, tag in link_targets]
                    self._logger.debug(f"Maintaining links with {target_names}")

                for target, tag in link_targets:
                    if target.pseudonym not in self.logical_links:
                        link = LogicalLink(
                            self._transport,
                            self._logger,
                            self.server_data,
                            self.private_key.public_key(),
                            target,
                            tag
                        )
                        self.logical_links[target.pseudonym] = link
                        nursery.start_soon(link.start)

                await trio.sleep(1.0)

    async def handle_link_request(self, nursery, request: PrismMessage, context: SpanContext):
        # TODO - verify request
        if request.pseudonym in self.logical_links:
            link = self.logical_links[request.pseudonym]
        else:
            link = LogicalLink(
                self._transport,
                self._logger,
                self.server_data,
                self.private_key.public_key(),
                request,
                request.whiteboard_ID,
            )
            self.logical_links[request.pseudonym] = link
            nursery.start_soon(link.start)

        await link.load_link_to(request, context)

    async def main(self):
        async with trio.open_nursery() as nursery:
            nursery.start_soon(super().main)
            if configuration.control_traffic:
                nursery.start_soon(self.ark_update_loop)
                nursery.start_soon(self.ark_listen_loop)
                nursery.start_soon(self.ark_broadcast_loop)
                nursery.start_soon(self.nark_broadcast_loop)

                if self.epoch != "genesis":
                    nursery.start_soon(self.link_maintenance_loop)
                    nursery.start_soon(
                        self.handler_loop,
                        nursery,
                        self.handle_link_request,
                        True,
                        TypeEnum.ENCRYPT_LINK_REQUEST
                    )
            else:
                await self.ls_routing.LSP_DB.update_routing_table()
                self.ls_routing.start_routing.set()

            nursery.start_soon(self.ls_routing.main_task)
