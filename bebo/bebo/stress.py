#  Copyright (c) 2019-2023 SRI International.

import argparse
import os
import random
import requests
import subprocess
import sys
import time
from typing import Dict, Set

from bebo.util import hostify, HTTP_PORT

class WriteFailed(Exception):
    pass

class TooManyAttempts(Exception):
    pass

def write(host: str, message: str):
    headers = {'Content-Type': 'application/octet-stream'}
    r = requests.post(f'http://{host}:{HTTP_PORT}/messages/write/',
                      data=message, headers=headers)
    if r.status_code != 201:
        raise WriteFailed(f'{host} {message!r} {r.status_code}')

def read(host: str, sequence_number: int):
    r = requests.get(f'http://{host}:{HTTP_PORT}/messages/readone/' +
                     f'{sequence_number}')
    if r.status_code == 200:
        return r.text
    else:
        return('FAILED')

def wait_for_text(url: str, text: str):
    attempts = 0
    while attempts < 30:
        try:
            attempts += 1
            r = requests.get(url)
            if r.status_code == 200:
                if r.text == text:
                    return
                else:
                    if attempts > 3:
                        print(url, 'expecting =', text, 'have =', r.text)
                    time.sleep(1)
            else:
                print(url, r.status_code)
                time.sleep(1)
        except Exception:
            time.sleep(1)
    raise TooManyAttempts(url)

def wait_for_all_connected(host: str, count: int):
    wait_for_text(f'http://{host}:{HTTP_PORT}/connected', str(count))

def wait_for_all_nonempty(host: str):
    wait_for_text(f'http://{host}:{HTTP_PORT}/allneighborsnonempty', '1')

def wait_for_all_received(host: str, count: int):
    wait_for_text(f'http://{host}:{HTTP_PORT}/messages/nextsequence',
                  str(count + 1))

def generate_neighbors(node_count: int, neighbor_count: int, v6: bool):
    # We only do all v4 or all v6 for simplicity in testing
    v4 = not v6
    table: Dict[str, Set[str]] = {}
    for i in range(1, node_count + 1):
        table[hostify(i, v4, v6)] = set()
    possibles = set(range(1, node_count + 1))
    for i in range(1, node_count + 1):
        possibles.remove(i)
        neighbors = set(random.sample(possibles, neighbor_count))
        possibles.add(i)
        # Add the neighbors we picked to i's entry
        table[hostify(i, v4, v6)].update([hostify(x, v4, v6)
                                          for x in neighbors])
        # Add an entry for i to each of the chosen neighbors.  We need
        # to do this so we have the right count to wait for later.
        for x in neighbors:
            table[hostify(x, v4, v6)].add(hostify(i, v4, v6))
    return table

def run(argv, testing=False) -> bool:
    parser = argparse.ArgumentParser(description='stress-test bebo')
    parser.add_argument('--servers', '-s', type=int, default=5,
                        metavar='N',
                        help='The number of bebo servers')
    parser.add_argument('--neighbors', '-n', type=int, default=2,
                        metavar='N',
                        help='The number of randomly chosen neighbors')
    parser.add_argument('--iterations', '-i', type=int, default=1,
                        metavar='N',
                        help='The number of iterations')
    parser.add_argument('--ipv6', '-6', action='store_true',
                        help='use IPv6')

    args = parser.parse_args(argv)

    iterations = args.iterations
    while iterations > 0:
        iterations -= 1
        neighbors = generate_neighbors(args.servers, args.neighbors, args.ipv6)
        for (k, v) in neighbors.items():
            print(k, v)
        processes = []
        good = False
        try:
            for (k, v) in neighbors.items():
                venv = os.environ.get('VIRTUAL_ENV', '')
                if 'poetry' in venv:
                    pargs = ['poetry', 'run', 'server']
                else:
                    pargs = ['python3', '-m', 'bebo.server']
                pargs.extend(['-a', k])
                pargs.extend(v)
                processes.append(subprocess.Popen(pargs))
            for k, v in neighbors.items():
                if args.ipv6:
                    k = f'[{k}]'
                wait_for_all_connected(k, len(v))
            for k in neighbors:
                if args.ipv6:
                    k = f'[{k}]'
                wait_for_all_nonempty(k)
            messages = set()
            for k in neighbors:
                message = f'injected at {k}'
                messages.add(message)
                if args.ipv6:
                    k = f'[{k}]'
                write(k, message)
            for k in neighbors:
                if args.ipv6:
                    k = f'[{k}]'
                wait_for_all_received(k, len(neighbors))
            for k in neighbors:
                if args.ipv6:
                    k = f'[{k}]'
                values = set()
                for i in range(1, args.servers + 1):
                    values.add(read(k, i))
                if values != messages:
                    print(k, values)
            good = True
        finally:
            for process in processes:
                process.kill()
                process.wait()
        if good:
            print('PASSED')
        else:
            print('FAILED')
            if testing:
                return False
            else:
                sys.exit(1)
    return True

def main():
    run(sys.argv[1:], False)

if __name__ == '__main__':
    main()
