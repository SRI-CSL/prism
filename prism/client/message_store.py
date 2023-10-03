#  Copyright (c) 2019-2023 SRI International.

from typing import List

from prism.common.cleartext import ClearText


class MessageStore:
    messages: List[ClearText]

    def __init__(self, configuration):
        self.config = configuration
        self.messages = []

    def record(self, message: ClearText):
        self.messages.append(message)

    def contacts(self):
        return {address
                for message in self.messages
                for address in [message.sender, message.receiver]
                if address != self.config.name}

    def received(self) -> List[ClearText]:
        return [message for message in self.messages if message.receiver == self.config.name]

    def conversations(self) -> dict:
        return {contact: self.conversation_with(contact) for contact in self.contacts()}

    def conversation_with(self, address: str) -> List[ClearText]:
        convo = [message for message in self.messages if message.sender == address or message.receiver == address]
        return sorted(convo, key=lambda m: m.timestamp)

