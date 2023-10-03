#  Copyright (c) 2019-2023 SRI International.

from prism.common.transport.transport import MessageHook, Package
from prism.common.message import ActionEnum, TypeEnum


class MPCResponseHook(MessageHook):
    op_id: bytes
    op_action: ActionEnum

    def __init__(self, pseudonym: bytes, party_id: int, op_id: bytes, op_action: ActionEnum = None):
        super().__init__()
        self.pseudonym = pseudonym
        self.party_id = party_id
        self.op_id = op_id
        self.op_action = op_action

    def match(self, package: Package) -> bool:
        message = package.message

        if message.msg_type != TypeEnum.MPC_RESPONSE:
            return False

        if message.pseudonym and message.pseudonym != self.pseudonym:
            return False

        if message.dest_party_id != self.party_id:
            return False

        if not message.mpc_map or message.mpc_map.request_id != self.op_id:
            return False

        if self.op_action and message.mpc_map.action != self.op_action:
            return False

        return True
