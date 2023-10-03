#  Copyright (c) 2019-2023 SRI International.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Any, Dict

from prism.common.pseudonym import Pseudonym
from prism.config.config import Configuration


@dataclass(order=True, eq=True, unsafe_hash=True)
class Node:
    name: str = field(compare=True)
    nat: bool = field(compare=True)
    enclave: str = field(default="global", compare=True)
    tags: Dict[str, Any] = field(default_factory=dict, compare=False)
    reachable: List[Node] = field(default_factory=list, compare=False)
    linked: List[Node] = field(default_factory=set, compare=False)
    testbed_idx: int = field(default=0)

    def pseudonym(self, config: Configuration) -> Pseudonym:
        return Pseudonym.from_address(self.name, config.prism_common["pseudonym_salt"])

    def config(self, config: Configuration) -> dict:
        from .bebo import Bebo
        whiteboards = [node.url for node in self.linked if isinstance(node, Bebo)]
        if whiteboards:
            return {
                "whiteboards": whiteboards,
            }
        else:
            return {}

    @property
    def client_ish(self) -> bool:
        from .client import Client
        from .server import Server, ClientRegistration
        return isinstance(self, Client) \
               or isinstance(self, Server) \
               and isinstance(self.role, ClientRegistration)
