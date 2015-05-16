#!/usr/bin/env python
# Copyright 2014, Rackspace US, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# (c) 2014, Kevin Carter <kevin.carter@rackspace.com>

import setuptools
import sys

import yaprt


with open('requirements.txt') as f:
    required = f.read().splitlines()

if sys.version_info < (2, 6, 0):
    sys.stderr.write("Python 2.6.0 or greater is required\n")
    raise SystemExit(
        '\nUpgrade python because you version of it is VERY deprecated\n'
    )
elif sys.version_info < (2, 7, 0):
    required.append('argparse')

with open('README.rst', 'r') as r_file:
    LDINFO = r_file.read()

setuptools.setup(
    name=yaprt.__appname__,
    version=yaprt.__version__,
    author=yaprt.__author__,
    author_email=yaprt.__email__,
    description=yaprt.__description__,
    long_description=LDINFO,
    license='License :: OSI Approved :: Apache Software License',
    packages=[
        'yaprt'
    ],
    url=yaprt.__url__,
    install_requires=required,
    classifiers=[
        yaprt.__status__,
        'Intended Audience :: Information Technology',
        'Intended Audience :: System Administrators',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Topic :: Utilities',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
    entry_points={
        "console_scripts": [
            "yaprt = yaprt.executable:main"
        ]
    }
)
