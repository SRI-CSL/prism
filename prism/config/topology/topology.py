#  Copyright (c) 2019-2023 SRI International.

from enum import Enum, auto
from typing import List

from prism.config.config import Configuration
from prism.config.environment.link import Link
from prism.config.environment.range import Range
from prism.config.environment.testbed import TestbedRange
from prism.config.error import ConfigError
from prism.config.topology.clustered import clustered
from prism.config.topology.ring import ring_topology
from prism.config.topology.single_whiteboard import single_whiteboard
from prism.config.topology.testbed import testbed_topology
from prism.config.topology.vrf import randomized


class PrismTopology(Enum):
    SINGLE_WHITEBOARD = auto()
    TESTBED = auto()
    CLUSTERED = auto()
    VRF = auto()
    RING = auto()


def build_topology(topology: str, test_range: Range, config: Configuration) -> List[Link]:
    topology = PrismTopology[topology]
    if topology == PrismTopology.SINGLE_WHITEBOARD:
        return single_whiteboard(test_range)
    elif topology == PrismTopology.TESTBED:
        config.prism_common["dynamic_links"] = False
        test_range: TestbedRange
        return testbed_topology(test_range)
    elif topology == PrismTopology.CLUSTERED:
        config.prism_common["dynamic_links"] = True
        config.prism_common["ls_routing"] = True
        return clustered(test_range, config)
    elif topology == PrismTopology.VRF:
        config.prism_common["dynamic_links"] = True
        config.prism_common["ls_routing"] = True
        return randomized(test_range, config)
    elif topology == PrismTopology.RING:
        config.prism_common["dynamic_links"] = True
        config.prism_common["ls_routing"] = True
        return ring_topology(test_range, config)
    else:
        raise ConfigError(f"Unsupported topology: {topology.name}")
