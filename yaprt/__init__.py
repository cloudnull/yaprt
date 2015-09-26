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

import os

__author__ = "Kevin Carter"
__contact__ = "Kevin Carter"
__email__ = "kevin.carter@rackspace.com"
__copyright__ = "2015 All Rights Reserved"
__license__ = "Apache2"
__date__ = "2015-07-07"
__version__ = "0.4.2"
__status__ = "Development Status :: 5 - Production/Stable"
__appname__ = "yaprt"
__description__ = 'Repository builder for python source code'
__url__ = 'https://github.com/cloudnull/yaprt.git'


# Requirements files types is a list of tuples that search for an online
# requirements files and where to file the found items. The tuple will be
# (TYPE, 'file name'). The type should directly correspond to a dict in
# PYTHON_PACKAGES
REQUIREMENTS_FILE_TYPES = [
    ('base_requirements', 'requirements.txt'),
    ('base_requirements', 'global-requirements.txt'),
    ('base_requirements', 'global_requirements.txt'),
    ('test_requirements', 'test-requirements.txt'),
    ('test_requirements', 'test_requirements.txt'),
    ('dev_requirements', 'dev-requirements.txt'),
    ('dev_requirements', 'dev_requirements.txt')
]

# This is used if no global gitconfig file is found for the executing user.
GITCONFIGBSAIC = """
[user]
        email = you@example.com
        name = Your Name
"""

# Arguments.
ARGUMENTS_DICT = {
    'shared_args': {
        'report_file': {
            'commands': [
                '--report-file'
            ],
            'help': 'Report json file. Default: %(default)s',
            'default': os.path.join(
                os.getenv('HOME'),
                'repo-requirements.json'
            )
        },
        'git_repo_path': {
            'commands': [
                '--git-repo-path'
            ],
            'help': 'Path to where to store all of the git repositories. If'
                    ' no path is set a path will be created in your temp'
                    ' directory.',
            'default': None
        }
    },
    'optional_args': {
        'mutually_exclusive': {
            'ops': {
                'text': 'Logging and STDOUT options',
                'required': False,
                'group': [
                    'quiet',
                    'debug'
                ]
            }
        },
        'quiet': {
            'commands': [
                '--quiet'
            ],
            'help': 'Enables quiet mode, this disables all stdout',
            'action': 'store_true',
            'default': False
        },
        'debug': {
            'commands': [
                '--debug'
            ],
            'help': 'Enable debug mode',
            'action': 'store_true',
            'default': False
        }
    },
    'subparsed_args': {
        'create-report': {
            'help': 'Create repository for all Openstack requirements.',
            'shared_args': [
                'report_file',
                'git_repo_path'
            ],
            'optional_args': {
                'groups': {
                    'report_options': {
                        'text': 'Optional report options',
                        'required': False,
                        'group': [
                            'report_file',
                            'git_install_repos',
                            'packages'
                        ]
                    }
                },
                'packages': {
                    'commands': [
                        '--packages'
                    ],
                    'nargs': '+',
                    'help': 'Name of the specific package to build into a'
                            ' report.',
                    'default': list()
                },
                'packages_file': {
                    'commands': [
                        '--packages-file'
                    ],
                    'help': 'Path to a file that contains a list of packages'
                            ' to build. This file should be, one package per'
                            ' line or separated by a white space.',
                    'default': None
                },
                'git_install_repos': {
                    'commands': [
                        '--git-install-repos'
                    ],
                    'nargs': '+',
                    'help': 'Full git install url with "branch/tag" within'
                            ' it.',
                    'default': list()
                },
                'git_install_repos_file': {
                    'commands': [
                        '--git-install-repos-file'
                    ],
                    'help': 'Path to a file that contains a list of git repos,'
                            ' with branch/tag, which will be built. This file'
                            ' should be, one package per line or separated by'
                            ' a white space',
                    'default': None
                }
            }
        },
        'build-wheels': {
            'help': 'Build all of the wheels from a json report.',
            'shared_args': [
                'report_file',
                'git_repo_path'
            ],
            'optional_args': {
                'groups': {
                    'github_auth': {
                        'text': 'Build options',
                        'required': False,
                        'group': [
                            'build_releases',
                            'build_branches',
                            'build_requirements',
                            'build_packages',
                            'build_output',
                            'build_dir'
                        ]
                    },
                    'storage_options': {
                        'text': 'Storage options',
                        'required': False,
                        'group': [
                            'link_dir',
                            'storage_pool'
                        ]
                    },
                    'pip_options': {
                        'text': 'Pip options',
                        'required': False,
                        'group': [
                            'pip_index',
                            'pip_extra_index',
                            'pip_no_deps',
                            'pip_no_index',
                            'pip_pre',
                            'pip_extra_link_dirs'
                        ]
                    }
                },
                'link_dir': {
                    'commands': [
                        '--link-dir'
                    ],
                    'help': 'Path to the build links for all built wheels.',
                    'default': None
                },
                'build_output': {
                    'commands': [
                        '--build-output'
                    ],
                    'help': 'Path to the location where the built Python'
                            ' package files will be stored.',
                    'required': True
                },
                'build_dir': {
                    'commands': [
                        '--build-dir'
                    ],
                    'help': 'Path to temporary build directory. If unset a'
                            ' auto generated temporary directory will be'
                            ' used.',
                    'default': None
                },
                'duplicate_handling': {
                    'commands': [
                        '--duplicate-handling'
                    ],
                    'help': 'When processing dependent packages choose how to'
                            ' handle the event of a duplicate package name'
                            ' with varying dependencies.',
                    'default': 'max',
                    'choices': ['max', 'min']
                },
                'pip_bulk_operation': {
                    'commands': [
                        '--pip-bulk-operation'
                    ],
                    'help': 'Attempt to build all of the requirements in one'
                            ' operation. Generally this is faster and will'
                            ' create less duplicates.',
                    'action': 'store_true',
                    'default': False
                },
                'pip_index': {
                    'commands': [
                        '--pip-index'
                    ],
                    'help': 'Index URL to override the main pip index.',
                    'default': 'https://pypi.python.org/simple/'
                },
                'pip_extra_index': {
                    'commands': [
                        '--pip-extra-index'
                    ],
                    'help': 'Extra Index URL to search.',
                    'default': None
                },
                'pip_no_deps': {
                    'commands': [
                        '--pip-no-deps'
                    ],
                    'help': 'Do not build package dependencies.',
                    'action': 'store_true',
                    'default': False
                },
                'pip_no_index': {
                    'commands': [
                        '--pip-no-index'
                    ],
                    'help': 'Ignore package index (only looking at'
                            ' --link-dir URLs instead).',
                    'action': 'store_true',
                    'default': False
                },
                'pip_pre': {
                    'commands': [
                        '--pip-pre'
                    ],
                    'help': 'Include pre-release and development versions.',
                    'action': 'store_true',
                    'default': False
                },
                'pip_extra_link_dirs': {
                    'commands': [
                        '--pip-extra-link-dirs'
                    ],
                    'nargs': '+',
                    'help': 'Path to source additional links from.',
                    'default': None
                },
                'storage_pool': {
                    'commands': [
                        '--storage-pool'
                    ],
                    'help': 'Path to the location where the built Python'
                            ' package files will be stored. This will be built'
                            ' out in simple Pypi index style.',
                    'required': True
                },
                'build_releases': {
                    'commands': [
                        '--build-releases'
                    ],
                    'help': 'Enable the building of wheels for all release'
                            ' tags from a prebuilt report',
                    'action': 'store_true',
                    'default': False
                },
                'build_branches': {
                    'commands': [
                        '--build-branches'
                    ],
                    'help': 'Enable the building of wheels for all branches in'
                            ' a prebuilt report',
                    'action': 'store_true',
                    'default': False
                },
                'build_packages': {
                    'commands': [
                        '--build-packages'
                    ],
                    'nargs': '+',
                    'help': 'Full name / path of a package to be built as a'
                            ' wheel. This can be any package name acceptable'
                            ' by pip',
                    'default': list()
                },
                'build_requirements': {
                    'commands': [
                        '--build-requirements'
                    ],
                    'help': 'Enable the building of wheels for all'
                            ' requirements in a prebuilt report.',
                    'action': 'store_true',
                    'default': False
                },
                'force_clean': {
                    'commands': [
                        '--force-clean'
                    ],
                    'help': 'Remove know wheels in the target links directory'
                            ' before building. This is a useful option when'
                            ' building in new versions of items within a given'
                            ' release.',
                    'action': 'store_true',
                    'default': False
                },
                'disable_version_sanity': {
                    'commands': [
                        '--disable-version-sanity'
                    ],
                    'help': 'Disabling version sanity removes version sanity'
                            ' checking and all packages will be built "as-is".'
                            ' This will produce a lot of duplicate packages'
                            ' though is useful when attempting to build a'
                            ' larger base repository.',
                    'action': 'store_true',
                    'default': False
                }
            }
        },
        'store-repos': {
            'help': 'Store all of the git source code in a given location.',
            'shared_args': [
                'report_file',
                'git_repo_path'
            ]
        },
        'create-html-indexes': {
            'help': 'Create an HTML index file for all folders and files'
                    ' recursively within a repo path.',
            'optional_args': {
                'repo_dir': {
                    'commands': [
                        '--repo-dir'
                    ],
                    'help': 'Path to the repository directory.',
                    'required': True,
                    'default': None
                },
                'dir_exclude': {
                    'commands': [
                        '--dir-exclude'
                    ],
                    'help': 'Path to the directories that you want to exclude'
                            ' indexes within.',
                    'nargs': '+',
                    'default': list()
                }
            }
        }
    }
}
