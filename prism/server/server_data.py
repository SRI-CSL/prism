#  Copyright (c) 2019-2023 SRI International.

from dataclasses import dataclass, field
from typing import Dict, Optional

from prism.common.message import HalfKeyMap, create_HKM, HalfKeyTypeEnum, PrismMessage
from prism.common.util import bytes_hex_abbrv


@dataclass(frozen=True, order=True)
class ServerData:
    id: str
    certificate: bytes = field(compare=False)
    DH_public_dict: Dict = field(compare=False)
    pseudonym: bytes = field(compare=False)
    role_name: str
    committee: str
    epoch: str
    proof: Optional[str]
    dropbox_index: Optional[int] = field(default=None, compare=False)

    def ark_data(self) -> dict:
        return {
            'certificate': self.certificate,
            'half_key': self.half_key_map(),
            'name': self.id,
            'pseudonym': self.pseudonym,
            'epoch': self.epoch,
            'committee': self.committee,
            'role': self.role_name,
            'proof': self.proof,
        }

    def __repr__(self):
        return f"(ID: {self.id}, pseudo: {bytes_hex_abbrv(self.pseudonym, 6)}, role: {self.role_name}" + \
               (f" ({self.dropbox_index})" if self.dropbox_index else "")

    def half_key_map(self) -> HalfKeyMap:
        return create_HKM(self.DH_public_dict, hkt=HalfKeyTypeEnum.ECDH)

    # @staticmethod
    # def from_message(message: PrismMessage):
    #     return ServerData(
    #         id=message.name,
    #         certificate=message.certificate,  # TODO: convert?
    #         DH_public_dict=message.half_key.as_cbor_dict()),
    #         pseudonym=message.pseudonym,
    #         role_name=message.role,
    #         committee=message.committee,
    #         epoch=message.epoch,
    #         proof=message.proof,
    #         dropbox_index=message.dropbox_index,
    #     )
