#  Copyright (c) 2019-2023 SRI International.

import os

NONCE_BYTES = 12
AES_KEY_BYTES = 32


def make_nonce():
    return os.urandom(NONCE_BYTES)


def make_aes_key():
    return os.urandom(AES_KEY_BYTES)
