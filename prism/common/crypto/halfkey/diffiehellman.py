#  Copyright (c) 2019-2023 SRI International.

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
import cryptography.hazmat.primitives.asymmetric.dh as dh
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
from typing import Dict, List

from .keyexchange import *

# Default system parameters
DH_MODULUS_BITS = 2048


class DiffieHellman(KeySystem):
    def __init__(self, key_size: int = DH_MODULUS_BITS):
        self.key_size: int = key_size
        self.params = None

    def generate_private(self) -> PrivateKey:
        if self.params is None:
            self.params = dh.generate_parameters(generator=2,
                                                 key_size=self.key_size,
                                                 backend=default_backend())

        return DHPrivateKey(self.params.generate_private_key())

    @staticmethod
    def load_private(data: bytes) -> PrivateKey:
        return DHPrivateKey(default_backend().load_pem_private_key(data, None))

    @staticmethod
    def load_public(cbor: dict) -> PublicKey:
        assert cbor[FIELD_KEY_TYPE] == KEY_TYPE_DH
        y = cbor[FIELD_DH_Y]
        parameter_numbers = dh.DHParameterNumbers(p=cbor[FIELD_DH_P],
                                                  g=cbor[FIELD_DH_G],
                                                  q=None)
        public_numbers = dh.DHPublicNumbers(y, parameter_numbers)
        public_key = public_numbers.public_key(default_backend())
        return DHPublicKey(public_key)

    @classmethod
    def load_system(cls, cbor: dict):
        parameter_numbers = dh.DHParameterNumbers(p=cbor[FIELD_DH_P],
                                                  g=cbor[FIELD_DH_G],
                                                  q=None)
        params = default_backend().load_dh_parameter_numbers(parameter_numbers)

        # TODO - Figure out key_size
        system = DiffieHellman()
        system.params = params

        return system

    @staticmethod
    def parameters_to_dict(params):
        parameter_numbers = params.parameter_numbers()
        return {FIELD_KEY_TYPE: KEY_TYPE_DH,
                FIELD_DH_P: parameter_numbers.p,
                FIELD_DH_G: parameter_numbers.g,
                FIELD_DH_Q: parameter_numbers.q}


class DHPublicKey(PublicKey):
    def __init__(self, public_key: dh.DHPublicKey):
        self.public_key = public_key

    def generate_private(self) -> PrivateKey:
        return DHPrivateKey(self.public_key.parameters().generate_private_key())

    def cbor(self) -> dict:
        params = self.public_key.parameters()
        d = DiffieHellman.parameters_to_dict(params)
        d[FIELD_DH_Y] = self.public_key.public_numbers().y
        return d

    def __str__(self):
        return f"DHPublicKey({self.cbor()})"


class DHPrivateKey(PrivateKey):
    def __init__(self, private_key: dh.DHPrivateKey):
        self.private_key: dh.DHPrivateKey = private_key

    def public_key(self) -> DHPublicKey:
        return DHPublicKey(self.private_key.public_key())

    def exchange(self, public_key: DHPublicKey, salt: bytes = None) -> bytes:
        shared_key = self.private_key.exchange(public_key.public_key)
        shared_int = int.from_bytes(shared_key, byteorder='big')
        shared_bytes = shared_int.to_bytes((shared_int.bit_length() + 8) // 8,
                                           byteorder='big',
                                           signed=True)

        return HKDF(algorithm=hashes.SHA256(),
                    length=AES_KEY_LENGTH_BYTES,
                    salt=salt,
                    info=b'prism halfkey',
                    backend=default_backend()).derive(shared_bytes)

    def serialize(self) -> bytes:
        return self.private_key.private_bytes(encoding=Encoding.PEM,
                                              format=PrivateFormat.PKCS8,
                                              encryption_algorithm=NoEncryption())

    def __str__(self):
        priv_nums = self.private_key.private_numbers()
        return f"DHPrivateKey({priv_nums.x})"


def public_dict_from_list(l: List) -> Dict:
    if len(l) != 4:
        raise ValueError("need exactly 4 items to create public dict")
    return {FIELD_KEY_TYPE: KEY_TYPE_DH, FIELD_DH_P: l[0], FIELD_DH_G: l[1], FIELD_DH_Q: l[2], FIELD_DH_Y: l[3]}
