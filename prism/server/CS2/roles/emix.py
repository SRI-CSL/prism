#  Copyright (c) 2019-2023 SRI International.
from jaeger_client import SpanContext
import trio
from typing import Tuple, List

from prism.common.transport.maintenance import incoming_links_task, outgoing_links_task
from prism.common.message import PrismMessage, TypeEnum
from prism.common.config import configuration
from prism.common.vrf.link import is_link_compatible
from .announcing_role import AnnouncingRole
from ...mixing.mix_strategies import get_mix


class Emix(AnnouncingRole, registry_name='EMIX'):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mix_strategy = get_mix(configuration.get('mix_strategy'), self)  # will choose DEFAULT if not specified

    async def mix_handler(self, nursery: trio.Nursery, message: PrismMessage, context: SpanContext):
        if message.msg_type == TypeEnum.LINK_REQUEST:
            nursery.start_soon(self.handle_client_link_request, context, message)
        else:
            submessage = PrismMessage.from_cbor_dict(message.sub_msg.as_cbor_dict())
            nursery.start_soon(self.mix_message, context, message, submessage)

    async def mix_message(self, context: SpanContext, decrypted: PrismMessage, submessage: PrismMessage):
        assert (decrypted.msg_type == TypeEnum.SEND_TO_EMIX and
                submessage.msg_type == TypeEnum.ENCRYPT_EMIX_MESSAGE) or \
               (decrypted.msg_type == TypeEnum.SEND_TO_DROPBOX and
                submessage.msg_type == TypeEnum.ENCRYPT_DROPBOX_MESSAGE)

        context = await self.mix_strategy.mix(submessage, context)

        with self.trace("mix-forward", context) as scope:
            retries = 0
            while not await self.emit(submessage, context=scope.context) and retries < configuration.mix_forward_retry_limit:
                scope.warning(f"Failed to emit message over next hop. "
                                     f"Retrying in {configuration.mix_forward_retry_delay_sec}s.")
                await trio.sleep(configuration.mix_forward_retry_delay_sec)
                retries += 1

            if retries >= configuration.mix_forward_retry_limit:
                scope.error(f"Could not forward message after {retries} attempts. Giving up.")

    async def handle_client_link_request(self, context: SpanContext, decrypted: PrismMessage):
        # TODO - authentication?
        with self.trace("link-request", context) as scope:
            scope.debug(f"Loading link to {decrypted.name}")
            address = decrypted.link_addresses[0]
            link = await self._transport.load_address(address, [decrypted.name], self.epoch)
            if not link:
                self._logger.error(f"Could not load requested link from address {address}")
                return

    def link_targets(self, seed: int) -> List[Tuple[PrismMessage, str]]:
        emixes = sorted([server for server in self.previous_role.flooding.payloads
                         if server.role == "EMIX"],
                        key=lambda s: s.pseudonym.hex())

        targets = set()

        probability = configuration.vrf_link_probability
        vrf_targets = [emix.pseudonym for emix in emixes
                       if is_link_compatible(self.pseudonym, emix.pseudonym, probability)]
        targets.update(vrf_targets)

        if configuration.vrf_topology_ring:
            my_index = next(i for i, emix in enumerate(emixes) if emix.pseudonym == self.pseudonym)
            ring_targets = [emixes[(my_index - 1) % len(emixes)].pseudonym,
                            emixes[(my_index + 1) % len(emixes)].pseudonym]
            targets.update(ring_targets)

        return [(emix, "lsp") for emix in emixes if emix.pseudonym in targets]

    async def main(self, caller_nursery: trio.Nursery = None) -> None:
        async with trio.open_nursery() as nursery:
            nursery.start_soon(super().main)
            nursery.start_soon(
                incoming_links_task,
                self._logger,
                self._transport,
                self.incoming_links,
                {"uplink"},
                self.epoch,
                "*uplink",
            )
            nursery.start_soon(
                outgoing_links_task,
                self._logger,
                self._transport,
                self.outgoing_links,
                {"ark"},
                self.epoch,
            )
            nursery.start_soon(self.handler_loop, nursery, self.mix_handler, True, TypeEnum.ENCRYPT_EMIX_MESSAGE)
