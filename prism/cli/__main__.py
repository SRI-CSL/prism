#  Copyright (c) 2019-2023 SRI International.

import argparse
from .command import CLICommand

parser = argparse.ArgumentParser(prog="prism")
subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

commands = CLICommand.load_commands()

for c in commands.values():
    c.extend_parser(subparsers)

args = parser.parse_args()
c = commands.get(args.command)

if c:
    c.run(args)
else:
    parser.print_help()
