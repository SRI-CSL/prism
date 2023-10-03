#  Copyright (c) 2019-2023 SRI International.

# Flooding API for sending ARKs (or other PrismMessage's) as payload to all other servers via (constrained) flooding
# or gossip-style (= limit number of) forwarding
import trio
from jaeger_client import SpanContext
import random
import structlog
from typing import *

from prism.common.config import configuration
from prism.common.logging import MONITOR_STATUS
from prism.common.message import PrismMessage, TypeEnum
from prism.common.tracing import trace_context
from prism.common.transport import transport as dt
from prism.common.transport.transport import Transport, MessageHook, Package
from prism.common.transport.enums import ConnectionType
from prism.common.util import bytes_hex_abbrv


class FloodHook(MessageHook):

    def match(self, package: Package) -> bool:
        msg = package.message
        return msg.msg_type in {TypeEnum.FLOOD_MSG}


class Flooding:

    def __init__(self, own_pseudonym: bytes, transport: Transport, epoch: str):
        assert own_pseudonym
        self.own_pseudonym = own_pseudonym
        self.epoch = epoch
        self._transport = transport
        self._database = {}  # type: Dict[bytes, PrismMessage]
        self._logger = structlog.getLogger(__name__).bind(myself=bytes_hex_abbrv(own_pseudonym), epoch=epoch)
        self._monitor_logger = structlog.get_logger(MONITOR_STATUS).bind(
            myself=bytes_hex_abbrv(self.own_pseudonym),
            epoch=epoch,
        )

    def __len__(self):
        return len(self._database)

    @property
    def payloads(self) -> List[PrismMessage]:
        return list(self._database.values())

    def link_filter(self, link: dt.Link) -> bool:
        return link.link_type.can_send \
               and link.connection_status.usable \
               and link.epoch == self.epoch \
               and (link.channel.connection_type == ConnectionType.DIRECT if configuration.flood_via_direct_only
                    else True)

    async def initiate(self, payload: PrismMessage):
        """ Initiate the flooding of given payload from this server. """
        assert payload
        flood_msg = PrismMessage(TypeEnum.FLOOD_MSG,
                                 originator=self.own_pseudonym, sender=self.own_pseudonym,
                                 hop_count=-1,
                                 sub_msg=payload)
        with trace_context(self._logger, "flood-initiated", epoch=self.epoch) as scope:
            scope.debug(f"Initiate FLOODING for epoch={self.epoch}")
            await self.handle_msg(flood_msg, scope.context)

    async def handle_msg(self, message: PrismMessage, context: SpanContext):
        if message.msg_type == TypeEnum.FLOOD_MSG:
            current_msg = self._database.get(message.originator, None)
            if current_msg is None:  # haven't seen this originator:
                # add message to database...
                current_payload = PrismMessage.from_cbor_dict(message.sub_msg.as_cbor_dict())
                self._database[message.originator] = current_payload
                with trace_context(self._monitor_logger, "flood-stored", epoch=self.epoch, db_size=len(self)) as scope:
                    scope.info(f'FLOODING database for epoch={self.epoch} has {len(self)} entries',
                               epoch=self.epoch,
                               originators=sorted([bytes_hex_abbrv(o) for o in self._database.keys()]),
                               n_db=len(self),)
                # ... then spread the news...
                if configuration.flood_max_hops and message.hop_count >= configuration.flood_max_hops:
                    self._logger.debug(f"Stop FLOODING because max hop count={configuration.flood_max_hops} reached")
                    return
                flood_msg = PrismMessage(TypeEnum.FLOOD_MSG,
                                         originator=message.originator,
                                         sender=self.own_pseudonym,
                                         hop_count=message.hop_count + 1,
                                         sub_msg=current_payload)
                with trace_context(self._logger, "flood-fwd", context,
                                   epoch=self.epoch, hop_count=flood_msg.hop_count) as scope:
                    scope.debug(f"Forwarding FLOODING for epoch={self.epoch}, " +
                                f"originator={bytes_hex_abbrv(message.originator)}, " +
                                f"hops={flood_msg.hop_count}")
                # collect link candidates from transport:
                filtered_links = list(filter(self.link_filter, self._transport.links_for_address("*")))
                # apply gossip R value (see server.toml for details)
                probability = configuration.flood_gossip_r if 0 < configuration.flood_gossip_r < 1 else 1
                if 1 <= configuration.flood_gossip_r < len(filtered_links):
                    # select this number of filtered links to forward to:
                    self._logger.debug(f"Reducing FLOODING links from {len(filtered_links)} " +
                                       f"to {configuration.flood_gossip_r}")
                    filtered_links = random.sample(filtered_links, configuration.flood_gossip_r)
                    assert probability == 1
                # apply flood_spread_seconds (if >0)
                sleep_times = [0.0] * len(filtered_links)
                if configuration.flood_spread_seconds > 0 and len(filtered_links) > 1:
                    a = [0.0] + sorted([random.uniform(0, configuration.flood_spread_seconds)
                                        for _ in range(len(filtered_links) - 1)])
                    sleep_times = [t - s for s, t in zip(a, a[1:])] + [0.0]
                assert len(sleep_times) == len(filtered_links)
                for filtered_link, sleep_time in zip(filtered_links, sleep_times):
                    if random.random() < probability:  # apply probability for each link
                        # NOTE: if we had a reliable way to match sender pseudonym against the endpoints of
                        #       filtered_link, we could optimize here by checking that we haven't received this
                        #       payload already from this destination...
                        if not await filtered_link.send(flood_msg, scope.context, ):  # TODO: timeout_ms?
                            self._logger.warning(f"FLOODING on link {filtered_link} didn't work!",
                                                 message=flood_msg)
                            # TODO: backlog this message and try again later?  For N times?
                        await trio.sleep(sleep_time)
            else:
                # we have already seen this originator...
                pass
        else:
            self._logger.warning(f"Don't know how to handle {message.msg_type}")

    async def flood_listen_loop(self):
        self._logger.debug(f'Starting Flooding listen task')
        flood_hook = FloodHook()
        await self._transport.register_hook(flood_hook)
        while True:
            package = await flood_hook.receive_pkg()
            await self.handle_msg(package.message, package.context)
