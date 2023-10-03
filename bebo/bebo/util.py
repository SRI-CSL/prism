#  Copyright (c) 2019-2023 SRI International.

import os
import socket

from typing import Any, Set, Optional

HTTP_PORT = 4000
HTTP_SEEDS_PORT = 4001

def af_for_text_address(address: str):
    try:
        socket.inet_pton(socket.AF_INET, address)
        return socket.AF_INET
    except OSError:
        socket.inet_pton(socket.AF_INET6, address)
        return socket.AF_INET6

def to_binary_address(address: str):
    try:
        return socket.inet_pton(socket.AF_INET, address)
    except OSError:
        return socket.inet_pton(socket.AF_INET6, address)

def to_text_address(address: bytes):
    if len(address) == 4:
        return socket.inet_ntop(socket.AF_INET, address)
    else:
        return socket.inet_ntop(socket.AF_INET6, address)

def is_text_address(value: Any):
    if not isinstance(value, str):
        return False
    try:
        to_binary_address(value)
        return True
    except Exception:
        return False

def hostify(arg, v4_ok=True, v6_ok=True) -> str:
    if isinstance(arg, int):
        arg = str(arg)
    if arg.find('.') == -1 and arg.isdigit():
        # XXXRTH This is for testing and should eventually be removed
        if v4_ok:
            return '10.53.0.' + arg
        if v6_ok:
            return 'fd53::' + arg
    infos = socket.getaddrinfo(arg, 0, type=socket.SOCK_STREAM,
                               flags=socket.AI_ADDRCONFIG)
    if v6_ok:
        # prefer the first IPv6 address
        for info in infos:
            if info[0] == socket.AF_INET6:
                return info[4][0]
    if v4_ok:
        # otherwise prefer the first IPv4 address
        for info in infos:
            if info[0] == socket.AF_INET:
                return info[4][0]
    raise ValueError(f'cannot hostify {arg}')

def my_addresses(name: Optional[str]=None) -> Set[str]:
    addresses: Set[str] = set()
    if name is not None:
        fqdn = socket.getfqdn(name)
    else:
        fqdn = socket.getfqdn()
    try:
        infos = socket.getaddrinfo(fqdn, 0, type=socket.SOCK_STREAM,
                                   flags=socket.AI_ADDRCONFIG)
        for info in infos:
            if info[0] in {socket.AF_INET, socket.AF_INET6}:
                addresses.add(info[4][0])
    except Exception:
        pass
    return addresses

def get_boolean_env(key, default=False):
    v = os.getenv(key)
    if v:
        if v.lower() in {'false', 'no', '0'}:
            return False
        else:
            return True
    else:
        return default

def get_int_env(key, default):
    v = os.getenv(key)
    if v:
        return int(v)
    else:
        return default

def get_version(debug):
    info = {
        'version': '0.0.0',
        'git_commit': 'unspecified',
        'git_branch': 'unspecified',
    }
    for filename in ['bebo/VERSION', 'VERSION']:
        if os.path.exists(filename):
            with open(filename) as f:
                for l in f.readlines():
                    l = l.rstrip()
                    parts = l.split('=')
                    if len(parts) == 2:
                        info[parts[0]] = parts[1]
            break
    text = f"{info['version']}"
    if debug:
        text += f" ({info['git_branch']} {info['git_commit']})"
    return text

def _render_row(offset, count, hex, annotation):
    r = count % 16
    if r != 0:
        count = 16 - r
        for i in range(count):
            hex += '   '
            annotation += ' '
    hex = hex[:-1]
    annotation = annotation[:-1]
    return f'{offset:08x} {hex} {annotation}\n'

def hexdump(binary):
    all = []
    hex = ''
    annotation = ''
    count = 0
    offset = 0
    for b in binary:
        count += 1
        hex += f'{b:02x} '
        c = chr(b)
        if b >= 128 or not c.isprintable():
            c = '.'
        annotation += c
        if count % 16 == 0:
            all.append(_render_row(offset, count, hex, annotation))
            hex = ''
            annotation = ''
            offset = count
    if hex:
        all.append(_render_row(offset, count, hex, annotation))
    return ''.join(all)
