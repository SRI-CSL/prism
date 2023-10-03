#  Copyright (c) 2019-2023 SRI International.

from __future__ import annotations

from prism.common.config import configuration
from prism.common.crypto.halfkey import EllipticCurveDiffieHellman
from prism.server.epoch import EpochState
from prism.server.epoch.epoch import Epoch


class GenesisEpoch(Epoch):
    def __init__(self, server, previous: Epoch):
        super().__init__("genesis", server, previous)
        self.configuration = configuration

        if "key_data" in configuration:
            self.private_key = EllipticCurveDiffieHellman.load_private(bytes.fromhex(configuration["key_data"]))
            self.public_key = self.private_key.public_key()

        if "pseudonym" in self.configuration:
            self.pseudonym = bytes.fromhex(self.configuration.pseudonym)

        self.role = self.generate_role()
        self.state = EpochState.RUNNING

    def generate_role(self):
        role_name = self.configuration.get("role", "dummy")

        # TODO - move into dropbox roles
        dropbox_index = self.configuration.get("db_index", None)

        committee = role_name
        if dropbox_index:
            committee += str(dropbox_index)

        return self.make_role(role_name, committee, dropbox_index, None)
