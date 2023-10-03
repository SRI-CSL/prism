#  Copyright (c) 2019-2023 SRI International.

from dataclasses import dataclass
from typing import List, Iterable

from prism.config.node.client import Client
from prism.config.node.node import Node
from prism.config.node.server import Server


@dataclass
class Enclave:
    name: str
    members: List[Node]

    def clients(self) -> List[Client]:
        return [node for node in self.members if isinstance(node, Client)]

    def servers(self) -> List[Server]:
        return [node for node in self.members if isinstance(node, Server)]

    def unclaimed_servers(self) -> Iterable[Server]:
        return [server for server in self.servers() if server.unclaimed()]
