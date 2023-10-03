
#  Copyright (c) 2019-2023 SRI International.

import requests
import sys

import bebo.util

def main():
    if len(sys.argv) > 1:
        host = bebo.util.hostify(sys.argv[1])
        if len(sys.argv) > 2:
            message = ' '.join(sys.argv[1:])
        else:
            message = 'test message'
    else:
        host = '127.0.0.1'
        message = 'test message'
    headers = {'Content-Type': 'application/octet-stream'}
    r = requests.post(f'http://{host}:{bebo.util.HTTP_PORT}/messages/write/',
                      data=message, headers=headers)
    print(r.status_code, r.text)

if __name__ == '__main__':
    main()
