#  Copyright (c) 2019-2023 SRI International.

from datetime import timedelta
from typing import List, Set

import trio

from prism.common.config import configuration
from prism.common.transport.channel_select import rank_channels
from prism.common.transport.enums import ConnectionType
from prism.common.transport.transport import Transport, Link
from prism.common.util import frequency_limit


async def incoming_links_task(
        logger,
        transport: Transport,
        links: List[Link],
        tags: Set[str],
        epoch: str,
        return_id: str
):
    while True:
        await trio.sleep(5.0)
        if configuration.dynamic_links:
            await maintain_incoming_links(logger, transport, links, tags, epoch, return_id)


async def maintain_incoming_links(
        logger,
        transport: Transport,
        links: List[Link],
        tags: Set[str],
        epoch: str,
        return_id: str
):
    epoch_links = [link for link in links if link.epoch == epoch]
    incoming_channels = [ch for ch in transport.channels if ch.link_direction.sender_loaded]

    if not incoming_channels and frequency_limit("incoming-channels-unavailable", timedelta(seconds=60)):
        logger.warn(f"No channels available to create incoming links.")

    channels_ranked = rank_channels(incoming_channels, ConnectionType.INDIRECT, tags)
    channels_to_use = channels_ranked[:configuration.incoming_channel_count]

    unused_channels = [channel for channel in channels_to_use
                       if channel.status.usable and
                       not any(link.channel.channel_id == channel.channel_id for link in epoch_links)]

    if not unused_channels:
        return

    new_channel = unused_channels[0]
    logger.debug(f"Creating incoming {tags} link on {new_channel}")
    new_link = await new_channel.create_link([return_id], epoch=epoch)

    if new_link:
        logger.debug(f"Created incoming {tags} link {new_link.link_id}, address: {new_link.link_address}")
        links.append(new_link)


async def outgoing_links_task(
        logger,
        transport: Transport,
        links: List[Link],
        tags: Set[str],
        epoch: str,
):
    while True:
        await trio.sleep(5.0)
        if configuration.dynamic_links:
            await maintain_outgoing_links(logger, transport, links, tags, epoch)


async def maintain_outgoing_links(logger, transport: Transport, links: List[Link], tags: Set[str], epoch: str):
    if links:
        return

    outgoing_channels = [ch for ch in transport.channels
                         if ch.link_direction.receiver_loaded and ch.connection_type.client_ok]
    channels_ranked = rank_channels(outgoing_channels, ConnectionType.INDIRECT, tags)

    if not channels_ranked:
        if frequency_limit("outgoing-channels-unavailable", timedelta(seconds=60)):
            logger.warn(f"No channels available to create outgoing links.")
        return

    if not channels_ranked[0].status.usable:
        logger.warn(f"Best channel {channels_ranked[0].channel_id} is not available, waiting...")
        return

    outgoing_link = await channels_ranked[0].create_link(["*downlink"], epoch=epoch)

    if outgoing_link:
        logger.debug(f"Created outgoing link {outgoing_link.link_id}, "
                     f"address: {outgoing_link.link_address}")
        links.append(outgoing_link)
