#  Copyright (c) 2019-2023 SRI International.

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, List, Tuple, Any

import structlog

from prism.common.config import configuration


class EpochCommandType(Enum):
    # Create a new epoch with given name and seed
    NEW = auto()
    # Instructs all epochs to transition to their next state
    NEXT = auto()
    # Instructs the specified epoch to end immediately
    OFF = auto()
    # Triggers immediate flooding of EARKs from the specified epoch
    FLOOD_EPOCH = auto()
    # Triggers immediate flooding of LSPs for the specified epoch
    FLOOD_LSP = auto()
    # Instructs all clients to poll immediately
    POLL = auto()
    # Instructs all nodes to make a config change
    CONFIG = auto()


@dataclass
class EpochCommand:
    command_type: EpochCommandType
    target_epoch_name: Optional[str]
    payload: List[str]

    @classmethod
    def parse_request(cls, epoch_data: str) -> Optional[EpochCommand]:
        logger = structlog.get_logger(__name__ + " > epoch_parse")

        try:
            logger.debug(f"epoch_data: {epoch_data}")
            req_parts = epoch_data.split()
            command_type = EpochCommandType[req_parts[0].upper()]
            target_epoch_name = None

            if command_type in [EpochCommandType.NEW, EpochCommandType.CONFIG]:
                payload = req_parts[1:]
            elif len(req_parts) > 1:
                target_epoch_name = req_parts[1]
                payload = req_parts[2:]
            else:
                payload = req_parts[1:]

            command = EpochCommand(command_type, target_epoch_name, payload)
            logger.debug(f"epoch command: {command}")
            return command
        except KeyError:
            logger.error(f"error parsing epoch command")
            return None

    def __repr__(self):
        return f"EpochCommand({self.command_type}, target: {self.target_epoch_name}, payload: {self.payload})"

    @property
    def epoch_seed(self) -> bytes:
        return self.payload[0].encode("utf-8")

    @property
    def config_data(self) -> Optional[Tuple[str, Any]]:
        from ast import literal_eval
        try:
            return self.payload[0], literal_eval(self.payload[1])
        except:
            return None

    def update_config(self, logger):
        config_data = self.config_data
        if not config_data:
            logger.warning(f"Couldn't extract valid config data from {self}.")
            return

        k, v = config_data
        logger.debug(f"Updating config, setting {k} = {v}")
        configuration[k] = v
