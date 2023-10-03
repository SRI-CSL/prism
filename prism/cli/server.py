#  Copyright (c) 2019-2023 SRI International.
from pathlib import Path

import trio

# local imports:
from prism.cli.command import CLICommand
from prism.common.state import DummyStateStore


def server_parser(parser):
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


def server(args):
    from prism.server.newserver import PrismServer
    from prism.common.transport.prism_transport import PrismTransport
    from prism.common.logging import init_logging, configure_logging
    from prism.common.config import init_config, configuration

    config_files = [Path(f) for f in args.config_files]
    init_logging()
    init_config(config_json=args.config_json, files=config_files)
    configure_logging("prism.server", configuration)
    transport = PrismTransport(configuration)
    prism = PrismServer(transport, DummyStateStore())
    try:
        trio.run(prism.main)
    except KeyboardInterrupt:
        pass


cli_command = CLICommand("server", server_parser, server, help="PRISM Server")
