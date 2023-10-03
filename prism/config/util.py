#  Copyright (c) 2019-2023 SRI International.

import re

camel_case_pattern = re.compile(r"(?<!^)(?=[A-Z])")


def snake_case(s: str) -> str:
    """Converts a camel-cased string to snake case."""
    return camel_case_pattern.sub("_", s).lower()
