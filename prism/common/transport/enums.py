#  Copyright (c) 2019-2023 SRI International.

from __future__ import annotations

from enum import Enum


class LinkDirection(Enum):
    UNDEF = 0
    CREATOR_TO_LOADER = 1
    LOADER_TO_CREATOR = 2
    BIDI = 3

    @property
    def receiver_loaded(self) -> bool:
        return self in [LinkDirection.BIDI, LinkDirection.CREATOR_TO_LOADER]

    @property
    def sender_loaded(self) -> bool:
        return self in [LinkDirection.BIDI, LinkDirection.LOADER_TO_CREATOR]


class TransmissionType(Enum):
    UNICAST = 1
    MULTICAST = 2

    def __str__(self):
        return self.name


class ConnectionType(Enum):
    UNDEF = 0
    DIRECT = 1
    INDIRECT = 2
    MIXED = 3
    LOCAL = 4

    def __str__(self):
        return self.name

    @property
    def client_ok(self) -> bool:
        return self in [ConnectionType.INDIRECT, ConnectionType.LOCAL]


class LinkType(Enum):
    UNDEF = 0
    SEND = 1
    RECV = 2
    BIDI = 3

    @property
    def can_send(self) -> bool:
        return self != LinkType.RECV

    @property
    def can_recv(self) -> bool:
        return self != LinkType.SEND


class ChannelStatus(Enum):
    UNDEF = 0
    AVAILABLE = 1
    UNAVAILABLE = 2
    ENABLED = 3
    DISABLED = 4
    STARTING = 5
    FAILED = 6
    UNSUPPORTED = 7

    @property
    def usable(self) -> bool:
        return self == ChannelStatus.AVAILABLE


class LinkStatus(Enum):
    CREATED = 1
    LOADED = 2
    DESTROYED = 3


class ConnectionStatus(Enum):
    INVALID = 0
    OPEN = 1
    CLOSED = 2
    AWAITING_CONTACT = 3
    INIT_FAILED = 4
    AVAILABLE = 5
    UNAVAILABLE = 6

    @property
    def usable(self) -> bool:
        return self in [ConnectionStatus.OPEN, ConnectionStatus.AVAILABLE]
