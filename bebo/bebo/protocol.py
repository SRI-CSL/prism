#  Copyright (c) 2019-2023 SRI International.

import base64
import cbor2    # type: ignore
import enum
import hashlib

from typing import Any, Dict, List, Optional

import bebo.util

@enum.unique
class MessageFields(enum.IntEnum):
    TYPE = 1
    MESSAGE = 2
    BROADCAST = 3
    NEIGHBORS = 4
    ERROR = 5

@enum.unique
class MessageType(enum.IntEnum):
    HANDSHAKE = 1
    RELAY = 2
    NEIGHBORS = 3

class Message:
    def __init__(self, broadcast: bool=True):
        self.broadcast = broadcast
        self.timestamp = None
        self.sequence_number = 0

    def size(self):
        return 0

class RelayMessage(Message):
    def __init__(self, message: bytes, broadcast=True):
        super().__init__(broadcast)
        self.message = message
        h = hashlib.sha256()
        h.update(message)
        self._sha256 = h.hexdigest()

    def key(self) -> str:
        return self._sha256

    def size(self) -> int:
        return len(self.message)

    def to_cbor(self) -> bytes:
        return cbor2.dumps({MessageFields.TYPE: MessageType.RELAY,
                            MessageFields.MESSAGE: self.message,
                            MessageFields.BROADCAST: self.broadcast})

    def mime_type(self) -> str:
        return 'application/octet-stream'

    def to_json(self) -> str:
        return base64.b64encode(self.message).decode('ascii')

    @classmethod
    def from_python(cls, value: Dict[Any, Any]):
        assert value[MessageFields.TYPE] == MessageType.RELAY
        try:
            message = value[MessageFields.MESSAGE]
        except KeyError:
            raise SyntaxError('No MESSAGE field')
        if not isinstance(message, bytes):
            raise SyntaxError('MESSAGE not a bytes')
        broadcast = value.get(MessageFields.BROADCAST, False)
        if not isinstance(broadcast, bool):
            raise SyntaxError('BROADCAST not a bool')
        return cls(message, broadcast)

    def __str__(self):
        return f'RelayMessage: {self.message} {self.broadcast}'

class NeighborsMessage(Message):
    def __init__(self, neighbors: List[str]):
        super().__init__(True)
        self.neighbors = neighbors

    def key(self) -> str:
        return f'neighbors message: {self.neighbors}'

    @classmethod
    def from_python(cls, value: Dict[Any, Any]):
        assert value[MessageFields.TYPE] == MessageType.NEIGHBORS
        try:
            neighbors = value[MessageFields.NEIGHBORS]
        except KeyError:
            raise SyntaxError('No NEIGHBORS field')
        if not isinstance(neighbors, list):
            raise SyntaxError('NEIGHBORS not a list')
        text_addresses = []
        for neighbor in neighbors:
            if not isinstance(neighbor, bytes):
                raise SyntaxError('neighbor is not a bytes')
            try:
                text_addresses.append(bebo.util.to_text_address(neighbor))
            except Exception:
                raise SyntaxError('neighbor is not an IP address')
        return cls(text_addresses)

    def to_cbor(self) -> bytes:
        binary_neighbors = [bebo.util.to_binary_address(x)
                            for x in self.neighbors]
        return cbor2.dumps({MessageFields.TYPE: MessageType.NEIGHBORS,
                            MessageFields.NEIGHBORS: binary_neighbors})

    def __str__(self):
        return f'NeighborsMessage: {self.neighbors}'

class HandshakeMessage(Message):
    def __init__(self, error: Optional[str]=None):
        super().__init__(True)
        self.error = error

    @classmethod
    def from_python(cls, value: Dict[Any, Any]):
        assert value[MessageFields.TYPE] == MessageType.HANDSHAKE
        error = value.get(MessageFields.ERROR)
        if error and not isinstance(error, str):
            raise SyntaxError('ERROR not a str')
        return cls(error)

    def to_cbor(self) -> bytes:
        msg: Dict[int, Any] = {MessageFields.TYPE: MessageType.HANDSHAKE}
        if self.error:
            msg[MessageFields.ERROR] = self.error
        return cbor2.dumps(msg)

    def __str__(self):
        return 'HandshakeMessage: {self.error}'

def from_python(value: Any) -> Message:
    if not isinstance(value, dict):
        raise SyntaxError('not a dictionary')
    msg_type = value.get(MessageFields.TYPE)
    if msg_type == MessageType.HANDSHAKE:
        return HandshakeMessage.from_python(value)
    elif msg_type == MessageType.RELAY:
        return RelayMessage.from_python(value)
    elif msg_type == MessageType.NEIGHBORS:
        return NeighborsMessage.from_python(value)
    elif msg_type is None:
        raise SyntaxError('no type field')
    else:
        raise SyntaxError(f'unknown type {msg_type}')

def from_cbor(cbor: bytes) -> Message:
    return from_python(cbor2.loads(cbor))
