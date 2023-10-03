#  Copyright (c) 2019-2023 SRI International.

from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from prism.common.crypto.util import make_aes_key, make_nonce


@dataclass
class EncryptedMessage:
    ciphertext: bytes
    key: bytes
    nonce: bytes


class DecryptException(BaseException):
    pass


class IdentityBasedEncryption(metaclass=ABCMeta):
    identity: str

    def __init__(self, identity: str):
        self.identity = identity

    def encrypt(self, address: str, plaintext: bytes) -> EncryptedMessage:
        key = make_aes_key()
        nonce = make_nonce()
        aes = AESGCM(key)

        ciphertext = aes.encrypt(nonce, plaintext, associated_data=None)
        encoded_key = self.encrypt_raw(address, key)
        encrypted = EncryptedMessage(ciphertext, encoded_key, nonce)

        return encrypted

    def decrypt(self, message: EncryptedMessage) -> bytes:
        key = self.decrypt_raw(message.key)
        try:
            aes = AESGCM(key)
            return aes.decrypt(message.nonce, message.ciphertext, associated_data=None)
        except:
            raise DecryptException

    @abstractmethod
    def encrypt_raw(self, address: str, plaintext: bytes) -> bytes:
        pass

    @abstractmethod
    def decrypt_raw(self, ciphertext: bytes) -> Optional[bytes]:
        pass

