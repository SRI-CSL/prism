#  Copyright (c) 2019-2023 SRI International.

import random
from typing import Union, List

from prism.common.crypto.secretsharing.secretsharing import SecretSharing
from prism.common.message import SecretSharingMap, SecretSharingType, Share


class FullThresholdSS(SecretSharing):

    def __init__(self, nparties: int, modulus: int):
        super(FullThresholdSS, self).__init__(
            SecretSharingMap(sharing_type=SecretSharingType.FULL,
                             parties=nparties, threshold=nparties, modulus=modulus))

    def share(self, value: Union[int, Share], coeff_required: bool = False) -> List[Share]:
        if isinstance(value, Share):
            value = value.share
        shares = []
        addedsum = 0
        for i in range(self.nparties - 1):
            ishare = random.randrange(1, self.modulus)
            addedsum += ishare
            shares.append(Share(ishare, i))
        shares.append(Share((value - addedsum) % self.modulus, self.nparties - 1))
        return shares

    def reconstruct(self, shares: List[Share], iq: int = 0, mode: int = 0) -> int:
        value = 0
        for share in shares:
            value += share.share
        return value % self.modulus

    def random_polynomial_root_at(self, iq: int) -> List[Share]:
        pass

    def commit(self, value: int) -> int:
        pass
