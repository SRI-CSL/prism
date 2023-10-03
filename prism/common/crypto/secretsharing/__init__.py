#  Copyright (c) 2019-2023 SRI International.

from prism.common.crypto.secretsharing.feldmans import FeldmansVSS
from prism.common.crypto.secretsharing.secretsharing import SecretSharing
from prism.common.crypto.secretsharing.shamir import ShamirSS
from prism.common.crypto.secretsharing.full_threshold import FullThresholdSS
from prism.common.message import SecretSharingMap, SecretSharingType


def get_ssobj(nparties, threshold, modulus, p=None, g=None) -> SecretSharing:
    if threshold - 1 < nparties/3 and p is not None and g is not None:
        return FeldmansVSS(nparties, threshold, modulus, p, g)
    # if threshold == nparties:
    #     return FullThresholdSS(nparties, modulus)
    return ShamirSS(nparties, threshold, modulus)


def get_ssobj_from_map(ss_map: SecretSharingMap) -> SecretSharing:
    assert ss_map
    assert ss_map.parties
    assert ss_map.threshold
    assert ss_map.modulus
    if ss_map.sharing_type == SecretSharingType.SHAMIR:
        return ShamirSS(ss_map.parties, ss_map.threshold, ss_map.modulus)
    if ss_map.sharing_type == SecretSharingType.FULL:
        if ss_map.parties != ss_map.threshold:
            raise ValueError("Cannot create Secret Sharing (Full) if not parties == threshold")
        return FullThresholdSS(ss_map.parties, ss_map.modulus)
    if ss_map.sharing_type == SecretSharingType.FELDMAN:
        assert ss_map.p
        assert ss_map.g
        return FeldmansVSS(ss_map.parties, ss_map.threshold, ss_map.modulus, ss_map.p, ss_map.g)
    raise ValueError(f"Cannot create Secret Sharing object from given map={ss_map}")
