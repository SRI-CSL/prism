#  Copyright (c) 2019-2023 SRI International.

from dataclasses import dataclass

from .node import Node


@dataclass(eq=True, unsafe_hash=True)
class Bebo(Node):
    BEBO_PORT = 4000
    outside_base_port: int = 8080

    @property
    def url(self):
        return f"http://{self.name}:{Bebo.BEBO_PORT}"

    @property
    def outside_port(self) -> int:
        return self.outside_base_port + self.testbed_idx

    @property
    def neighbors(self):
        return [node for node in self.linked if isinstance(node, Bebo)]
