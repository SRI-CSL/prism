#!/usr/bin/env python3

#  Copyright (c) 2019-2023 SRI International.

from dataclasses import dataclass
from datetime import datetime
from typing import List

import trio

from prism.client.web.remote import RemoteClient, ClearText
from prism.config.environment.testbed import TestbedRange
from prism.testbed.progress import Progress


@dataclass
class TestMessage:
    message: ClearText
    delay: float

    def to_json(self):
        return self.message.json()


class TestClient(RemoteClient):
    async def send_task(self, messages: List[TestMessage],
                        log: trio.MemorySendChannel):
        for msg in messages:
            await trio.sleep(msg.delay)
            await self.send_message(msg.message)
            await record(log, 'send',
                         sender=self.name,
                         recipient=msg.message.receiver,
                         message=msg.message.message)

    async def receive_task(self, expected_count: int,
                           log: trio.MemorySendChannel,
                           progress: Progress):
        for _ in range(expected_count):
            message = await self.get_message()
            await record(log, 'receive', **(message.json()))
            await progress.update()

    async def run_test(self, messages: List[TestMessage],
                       expected_count: int,
                       log: trio.MemorySendChannel,
                       progress: Progress):
        async with trio.open_nursery() as outer:
            outer.start_soon(self.listen)

            async with trio.open_nursery() as inner:
                inner.start_soon(self.send_task, messages, log)
                inner.start_soon(self.receive_task,
                                 expected_count, log, progress)

            self.quit()


def client_info(test_range: TestbedRange) -> List[TestClient]:
    """Builds a list of clients from the list of docker services."""
    return [TestClient(client.name, "localhost", client.outside_port) for client in test_range.clients]


async def record(log: trio.MemorySendChannel, event_type: str, **values):
    """Records an event to the log queue."""
    evt = {
        'event': event_type,
        'time': datetime.now(),
        **values
    }
    await log.send(evt)
