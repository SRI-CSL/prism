#  Copyright (c) 2019-2023 SRI International.
from enum import Enum, auto
from typing import Tuple

from .vrf import deserialize_proof, serialize_proof, VRF_verify, VRF_proof_to_hash, VRF_prove
from .octets import bytes2ip
from .distribution import VRFDistribution


class PrismSortition(Enum):
    STATIC = auto()
    VRF = auto()


class VRFSortition:
    def __init__(self, distribution: VRFDistribution):
        self.rd = distribution

    def sort_and_prove(self, sk, alpha: bytes) -> Tuple[str, str]:
        # SK is a cryptography secret key
        # alpha is type bytes (the payload)
        # pass proof and distribution to a sortition function to get a role
        # output the role and the proof
        pi = VRF_prove(sk, alpha)
        serial = serialize_proof(sk.public_key(), alpha, pi)
        h = bytes2ip(VRF_proof_to_hash(pi))
        return self.rd.role(h), serial

    def verify(self, serial_proof: str, role: str) -> bool:
        # input a serialized proof, claimed role, and a distribution
        pk, alpha, pi = deserialize_proof(serial_proof)
        if VRF_verify(pk, alpha, pi):
            beta = bytes2ip(VRF_proof_to_hash(pi))
            return self.rd.role(beta) == role
        else:
            return False
