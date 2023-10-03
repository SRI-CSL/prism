#  Copyright (c) 2019-2023 SRI International.

import cbor2
import requests
import sys
import base64

import bebo.util

def main():
    host = bebo.util.hostify(sys.argv[1])
    message = sys.argv[2]
    data = base64.b64decode(message)
    m2 = base64.b64encode(data)
    headers = {'Content-Type': 'application/octet-stream'}
    r = requests.post(f'http://{host}:{bebo.util.HTTP_PORT}/messages/write/',
                      data=data, headers=headers)
    print(r.status_code, r.text)

if __name__ == '__main__':
    main()
