#  Copyright (c) 2019-2023 SRI International.

import argparse

from prism.cli.command import CLICommand
from prism.aws import main as aws_main

LS_CHOICES = ["bebos", "clients"]


def aws_parser(parser: argparse.ArgumentParser):
    parser.add_argument("--param", "-P", metavar="PARAM=VALUE", action="append",
                        dest="param_overrides", default=[],
                        help="Override a parameter. May be specified multiple times.")
    parser.add_argument("--build", "-b", action="store_true",
                        help="Build the docker images before doing anything else.")
    parser.add_argument("-o", "--output-path", metavar="PATH", type=str, help="")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--ls", dest="lightsail", action='store_true',
                       help="AWS Lightsail deployment: generate clients' container services JSON files")
    group.add_argument("-l", "--local", dest="local", action='store_true',
                       help="Local docker-compose client deployment reaching out to AWS")
    group.add_argument("-k", "--k8s", dest="kubernetes", action='store_true',
                       help="K8s deployment: generate clients' configuration YAML files")
    parser.add_argument("scenarios", metavar="PARAMETER_FILES", type=argparse.FileType("r"), nargs="*",
                        help="Path to a json file containing AWS parameters.")


cli_command = CLICommand("aws", aws_parser, aws_main, help="PRISM AWS tests")
