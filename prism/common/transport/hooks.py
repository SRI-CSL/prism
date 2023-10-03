#  Copyright (c) 2019-2023 SRI International.

from typing import Iterable, Optional

from .transport import MessageHook, Package
from prism.common.message import TypeEnum


class MessageTypeHook(MessageHook):
    """Matches messages to the specified pseudonym of the specified types."""
    def __init__(self, pseudonym: Optional[bytes], *types: TypeEnum):
        super().__init__()
        self.pseudonym = pseudonym
        self.types = list(types)

    def match(self, package: Package) -> bool:
        message = package.message
        return (not self.pseudonym or message.pseudonym == self.pseudonym) and message.msg_type in self.types

    def __repr__(self) -> str:
        return f"MessageTypeHook({self.types})"
