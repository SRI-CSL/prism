#  Copyright (c) 2019-2023 SRI International.

import argparse

parser = argparse.ArgumentParser(description="Generate AWS Config Files")
required = parser.add_argument_group("Required Arguments")
optional = parser.add_argument_group("Optional Arguments")

# Required arguments
required.add_argument(
    "-o",
    "--output",
    dest="output_path",
    help="The directory to write configuration files to.",
    required=True,
    type=str,
)
required.add_argument(
    "--clients",
    dest="clients",
    metavar="CLIENT",
    nargs='+',
    help="List of client names to use",
)
required.add_argument(
    "--bebos",
    dest="bebos",
    metavar="URL",
    nargs='+',
    help="List of BEBO URLs to use (same length as --clients)",
)

# Optional Arguments
