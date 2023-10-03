
#  Copyright (c) 2019-2023 SRI International.

import requests
import sys

import bebo.util

def main():
    host = bebo.util.hostify(sys.argv[1])
    address = bebo.util.hostify(sys.argv[2])
    r = requests.delete(f'http://{host}:{bebo.util.HTTP_PORT}/neighbor/' +
                        f'{address}')
    print(r.status_code, r.text)

if __name__ == '__main__':
    main()
