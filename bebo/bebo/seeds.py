
#  Copyright (c) 2019-2023 SRI International.

import json
import random
import requests
import socket
import urllib.parse

from typing import Any, List, Optional, Set

import bebo.util

class Seeds:
    def __init__(self, text: Optional[str]=None, exclude=Optional[str]):
        self.all_seeds: Set[str] = set()
        self.seeds: Set[str] = set()
        if text:
            url = urllib.parse.urlparse(text)
            if url.scheme == 'http' or url.scheme == 'https':
                r = requests.get(text)
                if r.status_code == 200:
                    self.all_seeds = self.load_json(r.text)
                else:
                    raise ValueError('could not load seeds URL: ' +
                                     f'{r.status_code}')
            elif url.scheme == 'list':
                self.all_seeds = self.load_python({'seeds':
                                                   url.path.split(',')})
            elif url.scheme == 'file' or url.scheme == '':
                self.all_seeds = self.load_json_file(url.path)
        self.seeds.update(self.all_seeds)
        if exclude:
            self.seeds.discard(exclude)

    def choose(self, n: int) -> List[str]:
        n = min(n, len(self.seeds))
        return random.sample(self.seeds, n)

    def load_python(self, value: Any) -> Set[str]:
        seeds: Set[str] = set()
        hostname = socket.gethostname().lower()
        if not isinstance(value, dict):
            raise SyntaxError('top-level object is not a dictionary')
        if 'seeds' not in value:
            raise SyntaxError('no seeds key in configuration')
        text_seeds = value['seeds']
        if not isinstance(text_seeds, list):
            raise SyntaxError('seeds is not a list')
        for text_seed in text_seeds:
            # always skip our hostname
            if text_seed.lower() == hostname:
                continue
            seeds.add(bebo.util.hostify(text_seed))
        return seeds

    def load_json_file(self, filename: str) -> Set[str]:
        with open(filename) as f:
            return self.load_python(json.load(f))

    def load_json(self, text: str) -> Set[str]:
        return self.load_python(json.loads(text))
