#  Copyright (c) 2019-2023 SRI International.
from cbor2 import CBORDecodeError
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import structlog
from typing import Optional

from prism.common.crypto.halfkey.keyexchange import PrivateKey, PublicKey, KeySystem
from prism.common.message import PrismMessage

LOGGER = structlog.getLogger(__name__)


def decrypt(encrypted_msg: PrismMessage, private_key: PrivateKey, pub_key: PublicKey = None) -> Optional[PrismMessage]:
    plaintext = decrypt_data(encrypted_msg, private_key=private_key, pub_key=pub_key)
    if plaintext is not None:
        try:
            return PrismMessage.decode(plaintext)
        except CBORDecodeError:
            pass

    return None


def decrypt_data(encrypted_msg: PrismMessage, private_key: PrivateKey, pub_key: PublicKey = None) -> Optional[bytes]:
    if encrypted_msg.half_key:
        pub_key = KeySystem.load_public(encrypted_msg.half_key.as_cbor_dict())

    if pub_key and encrypted_msg.ciphertext and encrypted_msg.nonce:
        try:
            key = private_key.exchange(pub_key, b'')
            aes = AESGCM(key)
            plaintext = aes.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, associated_data=None)
            return plaintext
        except InvalidTag:
            # fall through to logging
            pass
    LOGGER.warning(f'Cannot decrypt {encrypted_msg}')
    return None


def encrypt(message: PrismMessage, private_key: PrivateKey, peer_key: PublicKey, nonce: bytes) -> bytes:
    assert message
    return encrypt_data(message.encode(), private_key, peer_key, nonce)


def encrypt_data(plaintext: bytes, private_key: PrivateKey, peer_key: PublicKey, nonce: bytes) -> bytes:
    assert private_key
    key = private_key.exchange(peer_key, b'')
    aes = AESGCM(key)
    return aes.encrypt(nonce, plaintext, associated_data=None)
