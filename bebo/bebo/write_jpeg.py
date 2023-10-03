
#  Copyright (c) 2019-2023 SRI International.

import requests
import sys

import bebo.util

def main():
    host = bebo.util.hostify(sys.argv[1])
    with open(sys.argv[2], 'rb') as f:
        message = f.read()
    headers = {'Content-Type': 'image/jpeg'}
    r = requests.post(f'http://{host}:{bebo.util.HTTP_PORT}/messages/write/',
                      data=message, headers=headers)
    print(r.status_code, r.text)

if __name__ == '__main__':
    main()
