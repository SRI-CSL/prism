#  Copyright (c) 2019-2023 SRI International.
import math
import random
import string
import sys
from typing import List

import trio

from prism.client.web.remote import RemoteClient
from prism.common.cleartext import ClearText
from prism.config.environment.testbed import TestbedDeployment
from prism.testbed.backend.docker import DockerBackend
from prism.testbed.client import client_info, TestMessage
from prism.testbed.params import TestParams
from prism.testbed.progress import Progress
from prism.testbed.report import drain_queue


def generate_test_messages(params: TestParams, clients: List[RemoteClient]) -> List[TestMessage]:
    def random_message():
        return ''.join([random.choice(string.ascii_letters)
                        for _ in range(params.message_length)])

    messages = []

    for sender in clients:
        for receiver in clients:
            if sender == receiver:
                continue

            for i in range(params.messages_per_pair):
                msg = ClearText(sender.name, receiver.name, random_message())
                messages.append(TestMessage(msg, params.message_delay_seconds))

    random.shuffle(messages)
    return messages


def client_messages(client: RemoteClient, test_messages: List[TestMessage]) -> List[TestMessage]:
    """Gets a list of messages for a particular client to send."""
    def p(msg: TestMessage):
        return msg.message.sender == client.name

    return list(filter(p, test_messages))


def expected_messages(client: RemoteClient,
                      test_messages: List[TestMessage]) -> int:
    """Calculates the number of messages a client is expecting to receive."""
    def p(msg: TestMessage):
        return msg.message.receiver == client.name

    return len(list(filter(p, test_messages)))


def docker_command(project: str, compose: str, *args) -> List[str]:
    """Creates a docker-compose command with given arguments."""
    cmd = ['docker-compose',
           '-p', project,
           '-f', compose]
    cmd.extend(args)
    return cmd


async def run_test(params: TestParams, deployment: TestbedDeployment) -> dict:
    if params.web_client:
        print("Testbed does not currently support web clients.")
        sys.exit(1)

    (event_send, event_receive) = trio.open_memory_channel(math.inf)

    clients = client_info(deployment.range)

    test_messages = generate_test_messages(params, clients)

    # Total timeout is the time it will take each sender to fully go through
    # its script, plus the timeout value from the config to let everything
    # settle and deliver messages.
    total_timeout = (params.message_delay_seconds *
                     params.messages_per_pair *
                     (params.client_count - 1) + params.timeout)

    progress = Progress(len(test_messages), total_timeout)

    results = {
        'test_messages': test_messages,
        'params': params,
        'clients': clients,
        'by_message': {},
        'send': [],
        'receive': [],
        'error': []
    }

    backend = DockerBackend(params, deployment.output_path / "docker-compose.json")

    with backend:
        # Wait for 3 seconds after docker-compose comes up to make sure sockets
        # are open by the time we want to connect to them.
        await trio.sleep(3)

        try:
            with trio.move_on_after(total_timeout):
                async with trio.open_nursery() as nursery:
                    nursery.start_soon(progress.run)

                    for client in clients:
                        messages = client_messages(client, test_messages)
                        expected = expected_messages(client, test_messages)

                        nursery.start_soon(client.run_test, messages,
                                           expected, event_send, progress)
        except trio.Cancelled:
            print(f"Timed out after {params.timeout} seconds.")
        except KeyboardInterrupt as ki:
            print("Interrupted.")
            params.pause_before_exit = False
            raise ki
        finally:
            drain_queue(results, event_receive)

    return results
