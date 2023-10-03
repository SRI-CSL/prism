#  Copyright (c) 2019-2023 SRI International.

from datetime import datetime
from typing import Optional

import trio
from jaeger_client import SpanContext

from prism.common.crypto.halfkey import PublicKey
from prism.common.crypto.server_message import encrypt
from prism.common.crypto.util import make_nonce
from prism.common.message import PrismMessage, TypeEnum, HalfKeyMap
from prism.common.tracing import trace_context
from prism.common.transport.channel_select import rank_channels
from prism.common.transport.enums import ConnectionType
from prism.common.transport.transport import Transport, Link
from prism.server.server_data import ServerData


class LogicalLink:
    def __init__(
            self,
            transport: Transport,
            logger,
            server_data: ServerData,
            public_key: PublicKey,
            target_eark: PrismMessage,
            tag: str
    ):
        self.transport = transport
        self.logger = logger
        self.own_name = server_data.id
        self.own_pseudonym = server_data.pseudonym
        self.public_key = public_key
        self.target_eark = target_eark
        self.endpoint_pseudonym = target_eark.pseudonym.hex()
        self.endpoint_name = target_eark.name
        self.epoch = server_data.epoch
        self.tag = tag
        self.control_link_address = target_eark.link_addresses[0]

        # TODO - smarter channel selection
        #  * support ConnectionType.MIXED
        #  * make sure channel is LoaderToCreator
        self.channel = rank_channels(self.transport.channels, ConnectionType.DIRECT, {tag})[0]
        self.control_link: Optional[Link] = None
        self.link_to: Optional[Link] = None
        self.link_from: Optional[Link] = None

    async def start(self):
        log_info = {"epoch": self.epoch, "target": self.endpoint_name}
        self.logger.debug(f"Starting logical link maintenance with {self.endpoint_name}", **log_info)

        if not self.link_from:
            self.logger.debug(f"Creating receive link for {self.endpoint_name}", **log_info)
            self.link_from = await self.channel.create_link(endpoints=[self.endpoint_name], epoch=self.epoch)
        if not self.control_link:
            if self.link_to:
                self.logger.debug(f"Reusing send link as control link for {self.endpoint_name}", **log_info)
                self.control_link = self.link_to
            else:
                self.logger.debug(f"Loading control plane link for {self.endpoint_name}", **log_info)
                self.control_link = await self.transport.load_address(
                    self.control_link_address,
                    [f"epoch-control"],
                    self.epoch
                )

        # TODO - longer term maintenance, better confirmation that the link was established
        #        currently, if a receive link gets reused we could see an erroneous "completed linkage"
        while self.link_from.last_receive == datetime.min:
            with trace_context(self.logger, "link-request", **log_info) as scope:
                request = self.make_link_request()
                scope.debug(f"Sending link request on {self.control_link}")
                await self.control_link.send(request, context=scope.context)
            await trio.sleep(60.0)

        self.logger.debug(f"Completed linkage with {self.endpoint_name}", **log_info)

    async def load_link_to(self, request: PrismMessage, context: SpanContext):
        if self.link_to:
            return

        with trace_context(self.logger, "handle-link-request", context,
                           epoch=self.epoch, target=self.endpoint_name) as scope:
            scope.debug(f"Loading send link for {self.endpoint_name}")
            self.link_to = await self.transport.load_address(
                request.link_addresses[0],
                [self.endpoint_name],
                self.epoch
            )
            self.control_link = self.link_to

            if self.link_to:
                scope.debug(f"Acknowledging link request from {self.endpoint_name}")
                await self.link_to.send(PrismMessage(TypeEnum.LINK_REQUEST_ACK))
            else:
                scope.warning(f"Failed to load link request from {self.endpoint_name} "
                              f"with address: {request.link_addresses}")

    def make_link_request(self) -> PrismMessage:
        inner_request = PrismMessage(
            TypeEnum.LINK_REQUEST,
            name=self.own_name,
            pseudonym=self.own_pseudonym,
            half_key=HalfKeyMap.from_key(self.public_key),
            link_addresses=[self.link_from.address_cbor],
            whiteboard_ID=self.tag,
        )

        private_key = self.target_eark.half_key.to_key().generate_private()
        nonce = make_nonce()

        outer_request = PrismMessage(
            TypeEnum.ENCRYPT_LINK_REQUEST,
            pseudonym=self.target_eark.pseudonym,
            nonce=nonce,
            half_key=HalfKeyMap.from_key(private_key.public_key()),
            ciphertext=encrypt(inner_request, private_key, self.target_eark.half_key.to_key(), nonce),
        )

        return outer_request
