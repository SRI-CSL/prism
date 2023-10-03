#  Copyright (c) 2019-2023 SRI International.

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Tuple

import structlog

from prism.common.config import configuration
from prism.common.server_db import ServerDB as CommonServerDB, ServerRecord
from prism.common.state import StateStore


@dataclass
class ServerStatus:
    reachable: bool = field(default=True)
    timestamp: datetime = field(default=datetime.utcfromtimestamp(0))

    @property
    def str_state(self) -> str:
        if self.reachable:
            return "alive"
        else:
            return "dead"

    def to_json(self) -> dict:
        return {
            "reachable": self.reachable,
            "timestamp": self.timestamp.timestamp()
        }

    @classmethod
    def from_json(cls, j: dict) -> ServerStatus:
        return ServerStatus(j["reachable"], datetime.utcfromtimestamp(j["timestamp"]))


class ServerDB(CommonServerDB):
    status_db: Dict[Tuple[bytes, bytes], ServerStatus]

    def __init__(self, state_store: StateStore, epoch: str):
        # Init status_db before super init, because it will be overridden by load()
        self.status_db = {}
        super().__init__(state_store=state_store, epoch=epoch)
        self._logger = structlog.get_logger(__name__)

    # FIXME -- use Pseudonyms instead of bytes
    def update_status(self, source: bytes, pseudonym: bytes, timestamp: datetime, reachable: bool):
        current_status = self.status_db.get((source, pseudonym))

        # Adjust death reports 5 seconds into the future to give them priority over life reports sent
        # in the same timeframe, because life reports get retransmitted and death reports do not.
        if not reachable:
            timestamp = timestamp + timedelta(seconds=5)

        new_status = ServerStatus(reachable, timestamp)

        if current_status and current_status.timestamp > timestamp:
            return

        if current_status and current_status.reachable != new_status.reachable:
            self._logger.debug(f"{source}: {pseudonym.hex()[:8]} "
                               f"was {current_status.str_state}, now {new_status.str_state}")

        self.status_db[(source, pseudonym)] = new_status

    def can_reach(self, a: ServerRecord, b: ServerRecord) -> bool:
        if not configuration.ls_routing:
            return True
        if not a.valid() or not b.valid():
            return False

        status = self.status_db.get((a.pseudonym, b.pseudonym))
        return status is None or status.reachable

    def to_json(self) -> dict:
        j = super().to_json()

        saved_status = []
        for (from_server, to_server), status in self.status_db.items():
            status_json = status.to_json()
            status_json["from"] = from_server.hex()
            status_json["to"] = to_server.hex()
            saved_status.append(status_json)

        j["status_db"] = saved_status

        return j

    def load(self, state: dict):
        super().load(state)

        if "status_db" in state:
            saved_status = state["status_db"]
            for status_json in saved_status:
                from_server = bytes.fromhex(saved_status["from"])
                to_server = bytes.fromhex(saved_status["to"])
                status = ServerStatus.from_json(status_json)
                self.status_db[(from_server, to_server)] = status
        else:
            # If no saved status DB (e.g. if loading from a pregenerated config generator ARK set),
            # assume every server is reachable from every other
            servers = list(self.servers.keys())
            for from_server, to_server in itertools.permutations(servers, 2):
                self.status_db[(from_server, to_server)] = ServerStatus(reachable=True, timestamp=datetime.utcnow())
