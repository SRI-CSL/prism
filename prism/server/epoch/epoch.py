#  Copyright (c) 2019-2023 SRI International.

from __future__ import annotations

import itertools
import structlog
import trio
from typing import Optional

from prism.common.crypto.halfkey import EllipticCurveDiffieHellman, PrivateKey, PublicKey
from prism.common.message import PrismMessage, TypeEnum, HalfKeyMap
from prism.common.pseudonym import Pseudonym
from prism.common.transport.channel_select import rank_channels
from prism.common.transport.enums import ConnectionType
from prism.common.transport.epoch_transport import EpochTransport
from prism.common.transport.transport import Link
from prism.server.CS2.roles import ClientRegistration, Emix
from prism.server.CS2.roles.abstract_role import AbstractRole
from prism.server.CS2.roles.announcing_role import AnnouncingRole
from prism.server.epoch import EpochState
from prism.server.pki import RoleKeyMaterial
from prism.server.server_data import ServerData


class Epoch:
    name: str
    previous: Optional[Epoch]
    key_material: RoleKeyMaterial
    role: AbstractRole
    state: EpochState

    serial_num_iterator = itertools.count()

    def __init__(self, name: str, server, previous: Epoch):
        self.serial_number = next(Epoch.serial_num_iterator)
        from prism.server.newserver import PrismServer
        server: PrismServer
        self.name = name
        self.server = server
        self.transport = EpochTransport(self.server.transport, self.name)
        self.previous = previous
        private_key = EllipticCurveDiffieHellman().generate_private()
        server_key, certificate, self.pseudonym = server.pki.fetch_key_cert_pseudonym(self.serial_number, server.name)
        self.key_material = RoleKeyMaterial(private_key, server_key, server.pki.root_cert, certificate)
        self.state = EpochState.PRE_RUN
        self.logger = structlog.get_logger(__name__ + f" > Epoch({self.name})")

        self.run_scope: Optional[trio.CancelScope] = None
        self.epoch_link: Optional[Link] = None
        self.epoch_ark: Optional[PrismMessage] = None

    @classmethod
    def from_seed(cls, server, previous: Optional[Epoch], seed: Optional[bytes]) -> Epoch:
        if previous and previous.role is ClientRegistration:
            return previous

        if not seed:
            from prism.server.epoch.genesis import GenesisEpoch
            return GenesisEpoch(server, previous)
        else:
            from prism.server.epoch.vrf import VRFEpoch
            return VRFEpoch(server, previous, seed)

    def make_role(
            self,
            role_name: str,
            committee: str,
            dropbox_index: int,
            proof: Optional[str]
    ):
        if self.previous:
            previous_role = self.previous.role
        else:
            previous_role = None

        return AbstractRole.create(
            role_name,
            epoch=self.name,
            transport=self.transport,
            state_store=self.server.state_store,
            sd=ServerData(
                id=self.server.name,
                certificate=self.key_material.server_cert_as_bytes(),
                DH_public_dict=self.key_material.private_key.public_key().cbor(),
                pseudonym=self.pseudonym,
                role_name=role_name,
                epoch=self.name,
                proof=proof,
                dropbox_index=dropbox_index,
                committee=committee,
            ),
            role_keys=self.key_material,
            previous_role=previous_role
        )

    async def start(self):
        if self.state == EpochState.PRE_RUN:
            await self.pre_run()
        elif self.state == EpochState.RUNNING:
            await self.run()
        else:
            self.server.logger.error(f"Starting epoch {self.name} in bad state: {self.state}")

    async def next_state(self, nursery: trio.Nursery):
        if self.state == EpochState.PRE_RUN:
            self.state = EpochState.RUNNING
            nursery.start_soon(self.run)
        elif self.state == EpochState.RUNNING:
            self.state = EpochState.HANDOFF
            # TODO - timed shutdown?
        elif self.state == EpochState.HANDOFF:
            self.state = EpochState.OFF
            self.logger.debug(f"Shutting down epoch {self.name}")
            await self.shutdown()
        else:
            pass

    async def pre_run(self):
        self.epoch_link = await self.make_epoch_link()
        self.epoch_ark = self.make_epoch_ark()
        if self.previous:
            await self.previous.flood_ark(self.epoch_ark)

    async def make_epoch_link(self):
        channels = [channel for channel in self.transport.channels if channel.link_direction.sender_loaded]
        ranked_channels = rank_channels(channels, connection_type=ConnectionType.INDIRECT, tags={"epoch"})
        best_channel = ranked_channels[0]
        return await best_channel.create_link([f"epoch-{self.name}"], self.name)

    def make_epoch_ark(self) -> PrismMessage:
        return PrismMessage(
            TypeEnum.EPOCH_ARK,
            name=self.server.name,
            pseudonym=self.pseudonym,
            role=self.role.role,
            committee=self.role.server_data.committee,
            half_key=HalfKeyMap.from_key(self.key_material.private_key.public_key()),
            epoch=self.name,
            link_addresses=[self.epoch_link.address_cbor]
        )

    async def flood_ark(self, epoch_ark: PrismMessage):
        self.logger.debug(f"Triggering flood of Epoch {self.name} ark")
        await self.role.flooding.initiate(epoch_ark)

    async def flood_lsp(self):
        self.logger.debug(f"Triggering LSP flood for Epoch {self.name}")
        # TODO - check if correct command
        self.role.ls_routing.trigger_aliveness()

    def print_flooded_earks(self):
        earks = sorted(self.previous.role.flooding.payloads, key=lambda e: e.name)
        self.logger.debug("EARKs flooded by previous roles:")
        for eark in earks:
            self.logger.debug(f"  {eark.name}, {eark.role}, {eark.committee}")

    async def run(self):
        if self.previous:
            self.print_flooded_earks()
            await self.handoff()

        with trio.CancelScope() as cancel_scope:
            self.run_scope = cancel_scope
            await self.role.main()

    async def handoff(self):
        """
        Called by incoming epoch. On servers that were previously Emixes, give them our new ARK store so that
        they can start informing clients of new epoch servers.
        """
        if isinstance(self.previous.role, Emix) and isinstance(self.role, AnnouncingRole):
            self.logger.debug(f"Requesting previous epoch {self.previous} broadcast new ARKs")
            # TODO - stop servers from clashing on ARK broadcast dates
            #        by wrapping ArkStore in class that tracks last broadcast separately
            new_arks = self.role.ark_store
            self.previous.role.handoff_arks(new_arks)

    async def shutdown(self):
        self.logger.debug(f"Shutting down Trio tasks for epoch {self.name}")
        if self.run_scope:
            self.run_scope.cancel()

        self.logger.debug(f"Shutting down links for epoch {self.name}")
        for channel in self.transport.channels:
            for link in channel.links:
                await link.close()

