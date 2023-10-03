#  Copyright (c) 2019-2023 SRI International.

from typing import Optional

from prism.common.crypto.ibe.ibe import IdentityBasedEncryption, EncryptedMessage
from prism.common.crypto.server_message import encrypt
from prism.common.crypto.util import make_nonce
from prism.common.message import PrismMessage, TypeEnum, CipherEnum, create_HKM
from prism.common.server_db import ServerRecord
from prism.common.tracing import extract_span_context, inject_span_context

EMIX_ROLES = ["EMIX"]
DROPBOX_ROLES = ["DROPBOX", "DROPBOX_LF"]


def encrypt_message(server: ServerRecord, message: PrismMessage, party_id: Optional[int] = None,
                    include_pseudonym: bool = False) -> PrismMessage:
    if server.role in EMIX_ROLES:
        message_type = TypeEnum.ENCRYPT_EMIX_MESSAGE
    elif server.role in DROPBOX_ROLES:
        message_type = TypeEnum.ENCRYPT_DROPBOX_MESSAGE
    else:
        message_type = TypeEnum.ENCRYPT_PEER_MESSAGE

    public_key = server.public_key(party_id)
    private_key = public_key.generate_private()
    nonce = make_nonce()
    ciphertext = encrypt(message, private_key, public_key, nonce)

    msg_fields = {
        "msg_type": message_type,
        "cipher": CipherEnum.AES_GCM,
        "ciphertext": ciphertext,
        "half_key": create_HKM(private_key.public_key().cbor()),
        "nonce": nonce,
    }

    if include_pseudonym is not None:
        msg_fields["pseudonym"] = server.pseudonym

    if party_id is not None:
        msg_fields["party_id"] = party_id

    return PrismMessage(**msg_fields)


def emix_forward(emix: ServerRecord, target: ServerRecord, message: PrismMessage) -> PrismMessage:
    if target.role in EMIX_ROLES:
        message_type = TypeEnum.SEND_TO_EMIX
    elif target.role in DROPBOX_ROLES:
        message_type = TypeEnum.SEND_TO_DROPBOX
    else:
        message_type = TypeEnum.SEND_TO_EMIX

    inner_message = PrismMessage(msg_type=message_type, sub_msg=message, hop_count=1)
    return encrypt_message(emix, inner_message, include_pseudonym=True)


def encrypt_user_message(
        ibe: IdentityBasedEncryption,
        address: str,
        message: PrismMessage,
) -> PrismMessage:
    encrypted = ibe.encrypt(address, message.encode())
    return PrismMessage(
        msg_type=TypeEnum.ENCRYPT_USER_MESSAGE,
        cipher=CipherEnum.AES_GCM,
        ciphertext=encrypted.ciphertext,
        nonce=encrypted.nonce,
        encrypted_msg_key=encrypted.key,
    )


def decrypt_user_message(
        ibe: IdentityBasedEncryption,
        message: PrismMessage,
) -> PrismMessage:
    context = extract_span_context(message)
    encrypted_message = EncryptedMessage(message.ciphertext, message.encrypted_msg_key, message.nonce)
    plaintext = ibe.decrypt(encrypted_message)
    message = PrismMessage.decode(plaintext)
    return inject_span_context(message, context)
