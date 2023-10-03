#  Copyright (c) 2019-2023 SRI International.
import random

import cbor2

from prism.common.crypto.secretsharing import get_ssobj
from prism.common.crypto.secretsharing.shamir import ShamirSS

modulus = 148642440876230622590087915555384503509593583704323618535892123042919637060567


def test_shamir_ss():
    ssobj = get_ssobj(4, 2, modulus)
    assert isinstance(ssobj, ShamirSS)


def test_share_bytes():
    ssobj = get_ssobj(4, 2, modulus)
    data = {'msg': b'Hello world, this is a test', 9: 'int key', "int_val": modulus}
    data_bytes = cbor2.dumps(data)
    shares = ssobj.share_bytes(data_bytes)
    reconstructed_bytes = ssobj.reconstruct_bytes(shares)
    reconstructed = cbor2.loads(reconstructed_bytes)

    assert reconstructed == data


def test_split_shares():
    ssobj = get_ssobj(4, 2, modulus)
    data = {'msg': b'Hello world, this is a test', 9: 'int key', "int_val": modulus}
    data_bytes = cbor2.dumps(data)
    shares = ssobj.share_bytes(data_bytes)
    packs = [ssobj.join_shares(pack) for pack in shares]
    shf = packs.copy()
    random.shuffle(shf)
    shf = shf[:-1]
    split_shares = [ssobj.split_shares(pack) for pack in shf]
    reconstructed_bytes = ssobj.reconstruct_bytes(split_shares)
    reconstructed = cbor2.loads(reconstructed_bytes)
    assert reconstructed == data
