#  Copyright (c) 2019-2023 SRI International.

from dataclasses import dataclass, field
from typing import FrozenSet, Optional, Iterable

from prism.config.node import Client, Server
from prism.config.node.node import Node
from prism.config.node.server import MPCDropbox
from prism.common.transport.enums import TransmissionType, ConnectionType


@dataclass(eq=True, unsafe_hash=True)
class Link:
    members: FrozenSet[Node] = field(compare=True)
    senders: FrozenSet[Node] = field(compare=True)
    receivers: FrozenSet[Node] = field(compare=True)
    tags: FrozenSet[str] = field(compare=True)
    connection_type: ConnectionType = field(compare=True)
    reliable: bool = field(compare=True)

    def __init__(
        self,
        members: Optional[Iterable[Node]] = None,
        senders: Optional[Iterable[Node]] = None,
        receivers: Optional[Iterable[Node]] = None,
        reliable=False,
        tags: Optional[Iterable[str]] = None,
        connection_type: ConnectionType = ConnectionType.INDIRECT,
    ):
        if members:
            self.members = frozenset(members)
            self.senders = self.members
            self.receivers = self.members
        else:
            self.senders = frozenset(senders)
            self.receivers = frozenset(receivers)
            self.members = self.senders.union(self.receivers)
        self.connection_type = connection_type
        self.tags = frozenset(tags or [])
        self.reliable = reliable

    def __repr__(self) -> str:
        return (
            f"Link({[node.name for node in self.senders]} -> {[node.name for node in self.receivers]},"
            f"{self.connection_type}, tags: {self.tags})"
        )

    def has_clients(self) -> bool:
        return any(isinstance(node, Client) for node in self.members)

    def is_mpc(self) -> bool:
        return all(isinstance(node, Server) and node.is_role(MPCDropbox) for node in self.members)

    def transmission_type(self) -> TransmissionType:
        if len(self.members) > 2:
            return TransmissionType.MULTICAST
        else:
            return TransmissionType.UNICAST
