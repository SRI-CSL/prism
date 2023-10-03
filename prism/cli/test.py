#  Copyright (c) 2019-2023 SRI International.

import argparse

from prism.cli.command import CLICommand
from prism.testbed import main as test_main


def test_parser(parser):
    parser.add_argument("--param", "-P", metavar="PARAM=VALUE", action="append",
                        dest="param_overrides", default=[],
                        help="Override a parameter. May be specified multiple times.")
    parser.add_argument("--build", "-b", action="store_true",
                        help="Build the docker images before running the test.")
    parser.add_argument("--no-test", action="store_true",
                        help="Bring up the docker range for poking and prodding, but don't run any tests.")
    parser.add_argument("--no-config", action="store_true",
                        help="Skip the config generation step (forces --no-test and disables --timestamped).")
    parser.add_argument("-o", "--output-path", metavar="PATH", type=str, help="")
    parser.add_argument("--timestamped", action="store_true", help="Create a timestamped run directory.")
    parser.add_argument("--generate", action="store_true",
                        help="Generate a run directory, then exit.")
    parser.add_argument("scenarios", metavar="PARAMETER_FILES", type=argparse.FileType("r"), nargs="*",
                        help="Path to a json file containing test parameters.")


cli_command = CLICommand("test", test_parser, test_main, help="Local testbed")
