#  Copyright (c) 2019-2023 SRI International.

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, NoEncryption, PrivateFormat
from typing import Dict, List

from .keyexchange import *


class EllipticCurveDiffieHellman(KeySystem):
    def generate_private(self) -> PrivateKey:
        return ECDHPrivateKey()

    @staticmethod
    def load_private(data: bytes) -> PrivateKey:
        key = X25519PrivateKey.from_private_bytes(data)
        return ECDHPrivateKey(key)

    @staticmethod
    def load_public(cbor: dict) -> PublicKey:
        assert cbor[FIELD_KEY_TYPE] == KEY_TYPE_ECDH
        data = cbor[FIELD_ECDH_PUBLIC]
        return ECDHPublicKey(X25519PublicKey.from_public_bytes(data))


class ECDHPublicKey(PublicKey):
    def __init__(self, public_key: X25519PublicKey):
        self.public_key = public_key

    def generate_private(self) -> PrivateKey:
        return ECDHPrivateKey()

    def cbor(self) -> dict:
        return {
            FIELD_KEY_TYPE: KEY_TYPE_ECDH,
            FIELD_ECDH_PUBLIC: self.serialize()
        }

    def serialize(self) -> bytes:
        return self.public_key.public_bytes(Encoding.Raw,
                                            PublicFormat.Raw)

    def __str__(self):
        return f"ECDHPublicKey({self.serialize().hex()})"


class ECDHPrivateKey(PrivateKey):
    def __init__(self, private_key: X25519PrivateKey = None):
        if private_key:
            self.private_key: X25519PrivateKey = private_key
        else:
            self.private_key: X25519PrivateKey = X25519PrivateKey.generate()

    def public_key(self) -> ECDHPublicKey:
        return ECDHPublicKey(self.private_key.public_key())

    def exchange(self, public_key: ECDHPublicKey, salt: bytes = None) -> bytes:
        secret = self.private_key.exchange(public_key.public_key)

        return HKDF(algorithm=hashes.SHA256(),
                    length=AES_KEY_LENGTH_BYTES,
                    salt=salt,
                    info=b'prism halfkey',
                    backend=default_backend()).derive(secret)

    def serialize(self) -> bytes:
        return self.private_key.private_bytes(Encoding.Raw,
                                              PrivateFormat.Raw,
                                              NoEncryption())

    def __str__(self):
        return f"ECDHPrivateKey({self.serialize().hex()})"


def public_dict_from_list(l: List) -> Dict:
    if len(l) != 1:
        raise ValueError("need exactly 1 item to create public dict")
    return {FIELD_KEY_TYPE: KEY_TYPE_ECDH, FIELD_ECDH_PUBLIC: l[0]}
