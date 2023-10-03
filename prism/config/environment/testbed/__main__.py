#  Copyright (c) 2019-2023 SRI International.

from .args import parser
from . import generate_config

main_args = parser.parse_args()
generate_config(main_args)
