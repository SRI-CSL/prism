#!/usr/bin/env python3

#  Copyright (c) 2019-2023 SRI International.

from setuptools import setup, find_packages
from pathlib import Path
import os

vfile = Path(__file__).parent / "VERSION"
VERSION = vfile.read_text().strip()

setup(
    name='prism',
    version=VERSION,
    scripts=["bin/prism"],
    packages=find_packages(include=['prism', 'prism.*'])
)
