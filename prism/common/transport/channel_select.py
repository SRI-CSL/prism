#  Copyright (c) 2019-2023 SRI International.

from typing import Set, List

from prism.common.config import configuration
from prism.common.transport.enums import ConnectionType
from prism.common.transport.transport import Channel


def rank_channels(channels: List[Channel], connection_type: ConnectionType, tags: Set[str]) -> List[Channel]:
    """
    Rank available channels by suitability for a connection.
    Channels that don't match the supplied connection type will be dropped.
    After that, channels are ranked by number of matching tags, then by latency, then by bandwidth.
    """

    channels = [channel for channel in channels
                if channel.connection_type == connection_type]

    # Sort in reverse order of key priority
    channels.sort(key=lambda c: c.bandwidth_bps, reverse=True)
    channels.sort(key=lambda c: c.latency_ms, reverse=True)

    if configuration.strict_channel_tags:
        channels = [c for c in channels if tags.intersection(c.tags)]
    else:
        channels.sort(key=lambda c: len(tags.intersection(c.tags)), reverse=True)

    return channels
