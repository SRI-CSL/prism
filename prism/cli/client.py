#  Copyright (c) 2019-2023 SRI International.

from pathlib import Path

import trio

from prism.cli.command import CLICommand
from prism.common.state import DummyStateStore


def client_parser(parser):
    parser.add_argument(
        '-j',
        metavar='JSON',
        dest='config_json',
        help='string with settings for PRISM in JSON format (applied first)'
    )
    parser.add_argument(
        "config_files",
        metavar='FILE',
        nargs='*',
        help='file(s) with settings for PRISM in toml|yaml|json|ini format (applied second and in order)'
    )


def client(args):
    import trio
    from prism.common.config import init_config, configuration
    from prism.common.logging import init_logging, configure_logging
    from prism.common.transport.prism_transport import PrismTransport
    from prism.client.client import PrismClient

    config_files = [Path(f) for f in args.config_files]

    init_logging()
    init_config(config_json=args.config_json, files=config_files)
    configure_logging("prism.client", configuration)
    transport = PrismTransport(configuration)
    prism_client = PrismClient(transport, DummyStateStore())

    trio.run(run_client, prism_client, transport)


async def run_client(prism_client, transport):
    async with trio.open_nursery() as nursery:
        nursery.start_soon(transport.run)
        nursery.start_soon(prism_client.start)


cli_command = CLICommand("client", client_parser, client, help="PRISM Client (inside Docker only)")
