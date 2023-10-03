#  Copyright (c) 2019-2023 SRI International.

from enum import Enum, auto


class EpochState(Enum):
    # An epoch in the PRE_RUN state creates its epoch receive link, generates an epoch ARK,
    # and requests its ancestor epoch to flood the epoch ARK.
    PRE_RUN = auto()
    # A running epoch builds connections to VRF-selected peers and runs as normal
    RUNNING = auto()
    # A transitioning epoch doesn't buy any unripe bananas
    HANDOFF = auto()
    # An epoch that has ended
    OFF = auto()