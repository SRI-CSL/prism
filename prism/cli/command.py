#  Copyright (c) 2019-2023 SRI International.

from __future__ import annotations
from typing import Dict


class CLICommand:
    def __init__(self, name: str, parser, runner, **kwargs):
        self.name = name
        self.parser = parser
        self.runner = runner
        self.kwargs = kwargs
        self.aliases = kwargs.get('aliases', [])

    def run(self, args):
        self.runner(args)

    def extend_parser(self, subparsers):
        parser = subparsers.add_parser(self.name, **self.kwargs)
        self.parser(parser)

    @staticmethod
    def load_commands() -> Dict[str, CLICommand]:
        import importlib
        import pkgutil
        import prism.cli

        commands = {}

        for module in pkgutil.iter_modules(prism.cli.__path__):
            if module.name == "__main__":
                continue

            m = importlib.import_module(f".{module.name}", package=__package__)
            if hasattr(m, "cli_command"):
                c: CLICommand = m.cli_command
                commands[c.name] = c
                for alias in c.aliases:
                    commands[alias] = c

        return commands
