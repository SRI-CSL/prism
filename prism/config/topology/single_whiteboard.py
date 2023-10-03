#  Copyright (c) 2019-2023 SRI International.

from typing import List

from prism.config.environment import Range
from prism.config.environment.link import Link
from prism.common.transport.enums import ConnectionType


def single_whiteboard(test_range: Range) -> List[Link]:
    """Everyone is connected to a single, global whiteboard. No other links exist."""
    return [Link(members=test_range.nodes.values(), connection_type=ConnectionType.INDIRECT)]
