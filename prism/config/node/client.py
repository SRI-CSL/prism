#  Copyright (c) 2019-2023 SRI International.

from dataclasses import dataclass, field
from typing import List

from prism.config.config import Configuration
from prism.config.ibe.ibe import IBE
from prism.config.node.node import Node


@dataclass(eq=True, unsafe_hash=True)
class Client(Node):
    ibe: IBE = field(default=None, compare=False)
    contacts: List[str] = field(default_factory=list, compare=False)

    outside_base_port: int = 7000

    def config(self, config: Configuration) -> dict:
        return {
            **super().config(config),
            **self.ibe.node_config(self.name),
            "contacts": self.contacts,
            "is_client": True,
        }

    @property
    def outside_port(self) -> int:
        return self.outside_base_port + self.testbed_idx
