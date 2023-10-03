
#  Copyright (c) 2019-2023 SRI International.

import requests
import sys

import bebo.util

def main():
    sequence_number = '1'
    if len(sys.argv) > 1:
        host = bebo.util.hostify(sys.argv[1])
        if len(sys.argv) > 2:
            sequence_number = sys.argv[2]
    else:
        host = '127.0.0.1'

    r = requests.get(f'http://{host}:{bebo.util.HTTP_PORT}/messages/' +
                     f'readone/{sequence_number}')
    if r.status_code == 200:
        print(r.text)
    else:
        print('error', r.status_code)

if __name__ == '__main__':
    main()
