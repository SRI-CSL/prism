#!/usr/bin/env python3

#  Copyright (c) 2019-2023 SRI International.

import argparse
import base64
import json
import requests
import sys

def checked_get(url):
    r = requests.get(url)
    if r.status_code != 200:
        print(f'error fetching {url}:', r.status_code, file=sys.stderr)
        sys.exit(1)
    return json.loads(r.text)

def print_row(offset, count, hex, annotation):
    r = count % 16
    if r != 0:
        count = 16 - r
        for i in range(count):
            hex += '   '
            annotation += ' '
    hex = hex[:-1]
    annotation = annotation[:-1]
    print(f'{offset:08x}', ' ', hex, ' ', annotation)

def hexdump(binary):
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
            print_row(offset, count, hex, annotation)
            hex = ''
            annotation = ''
            offset = count
    if hex:
        print_row(offset, count, hex, annotation)

def main():
    parser = argparse.ArgumentParser(description='bebo message dumper')
    parser.add_argument('--server', '-s', metavar='SERVER', default='127.0.0.1',
                        help='the BEBO server hostname or IP address')
    parser.add_argument('--port', '-p', metavar='PORT', default=4000,
                        type=int, help='the BEBO port to query')
    parser.add_argument('--count', '-c', metavar='NUMBER', default=1,
                        type=int, help='the number of messages to retrieve')
    parser.add_argument('--first', '-f', metavar='NUMBER', default=0,
                        type=int, help='the first message to retrieve')
    args = parser.parse_args(sys.argv[1:])
    url = f'http://{args.server}:{args.port}/message?count=0'
    info = checked_get(url)
    least = info.get('least')
    greatest = info.get('greatest')
    if least is None or greatest is None:
        print('no messages on whiteboard', file=sys.stderr)
        sys.exit(2)
    if args.first:
        first = args.first
        count = args.count
    elif args.count:
        # get the last <count> messages
        first = max(1, greatest - args.count + 1)
        count = greatest - first + 1
    else:
        first = greatest
        count = 1
    url = f'http://{args.server}:{args.port}/message' + \
        f'?first={first}&count={count}'
    info = checked_get(url)
    want_blank = False
    for minfo in info['messages']:
        if want_blank:
            print()
        print('message', minfo['id'])
        print()
        hexdump(base64.b64decode(minfo['message']))
        want_blank = True

if __name__ == '__main__':
    main()
