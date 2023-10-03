#  Copyright (c) 2019-2023 SRI International.
import hashlib
from datetime import datetime, timedelta
from typing import Dict

PREFIX_LENGTH = 8


def bytes_hex_abbrv(bytes_to_render: bytes, length: int = 0) -> str:
    return bytes_to_render.hex()[:(length if length else PREFIX_LENGTH)] if bytes_to_render else 'None'


def is_jpeg(data):
    return (data.startswith(b'\xff\xd8\xff\xe0') or
            data.startswith(b'\xff\xd8\xff\xee'))


def hash_data(data: bytes) -> str:
    sha = hashlib.sha256()
    sha.update(data)
    return sha.hexdigest()


def posix_utc_now():
    return int(datetime.utcnow().timestamp())


def datafy(cls, dct):
    """
    Convert a dictionary into a dataclass, discarding any fields that the dataclass doesn't support so we don't raise
    an exception.
    """
    fields = {k: v for k, v in dct.items() if k in cls.__dataclass_fields__}
    return cls(**fields)


frequency_limit_times: Dict[str, datetime] = {}


def frequency_limit(category: str, limit: timedelta = timedelta(seconds=30)) -> bool:
    """
    Returns True if it hasn't been called with category in the last limit seconds. Useful for error messages that are
    frequently generated and would otherwise fill the logs with spam.

    example usage:

    while True:
        if frequency_limit("category", timedelta(seconds=60):
            thing_you_only_want_to_do_once_per_minute()
        await trio.sleep(0.1)
    """
    global frequency_limit_times
    last_action = frequency_limit_times.get(category, datetime.min)

    if datetime.utcnow() > last_action + limit:
        frequency_limit_times[category] = datetime.utcnow()
        return True

    return False


def report_error(logger, category, _exception):
    import traceback
    trace = traceback.format_exc()
    logger.error(f"Error in {category}: {trace}")