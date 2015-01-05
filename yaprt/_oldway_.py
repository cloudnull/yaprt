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

import argparse
import datetime
import json
import os
import subprocess
import tempfile
import urlparse

from distutils import version

import requests
import yaml

from cloudlib import logger
from cloudlib import indicator


"""Rackspace Private Cloud python wheel builder.

This script is a simple python wheel building application that will read
in yaml files that contain references to git repos and lists of python packages
and then search for all things python that could be installed using pip.
Anything discovered to be a python package will be build as a Python wheel.

The reason that Python wheels were chosen as a method for packaging is simply
tied to upstream support in addition to simplicity. Python wheels are supported
in modern mainstream python and result in a more stable method of installation
without the requirement of having to compile on the installation target.


The YAML syntax for repo pacakge files is simple:
    ## Git Source
    git_repo: https://github.com/USERNAME/REPOSITORY
    git_install_branch: BRANCH|TAG|SHA

    service_pip_dependencies:
      - pywbem
      - ecdsa
      - MySQL-python
      - python-memcached
      - pycrypto
      - python-cinderclient
      - python-keystoneclient
      - keystonemiddleware
      - httplib2


This script will build all of the wheels for everything in the
``service_pip_dependencies`` array and scan the git repo for any requirement
file as found in the constant ``REQUIREMENTS_FILE_TYPES`` here within the
script. Pip dependencies can be a member of any variable found in the constant
``BUILT_IN_PIP_PACKAGE_VARS`` here within the script.

Other git repo types can be added to the script by updating the
``GIT_REQUIREMENTS_MAP`` constant with an appropriate mapping to where RAW
files can be found.

Upon completion of the script a pools directory will be updated with all of the
built wheels. The release provided will be a directory full of links pointing
back to the built wheels for the release. This allows you to have multiple
releases with different requirements while also not rebuilding wheels that
already exist.
"""


PYTHON_PACKAGES = {
    'base_release': dict(),
    'known_release': dict(),
    'from_git': dict(),
    'required_packages': dict(),
    'test_requirements': dict(),
    'built_files': list()
}

GIT_REPOS = list()


# Templates for online git repositories that we scan through in order to
# discover requirements files and installable python packages.
GIT_REQUIREMENTS_MAP = {
    'github.com': 'https://raw.githubusercontent.com/%(path)s/%(branch)s'
                  '/%(file)s',
    'openstack.org': 'https://git.openstack.org/cgit/%(path)s/plain'
                     '/%(file)s?id=%(branch)s'
}


# List of variable names that could be used within the RPC yaml files that
# represent lists of python packages.
BUILT_IN_PIP_PACKAGE_VARS = [
    'service_pip_dependencies',
    'pip_common_packages',
    'pip_container_packages',
    'pip_packages'
]

# Requirements files types is a list of tuples that search for an online
# requirements files and where to file the found items. The tuple will be
# (TYPE, 'file name'). The type should directly correspond to a dict in
# PYTHON_PACKAGES
REQUIREMENTS_FILE_TYPES = [
    ('base_release', 'requirements.txt'),
    ('base_release', 'global-requirements.txt'),
    ('test_requirements', 'test-requirements.txt'),
    ('test_requirements', 'dev-requirements.txt')
]


VERSION_DESCRIPTORS = [
    '>=', '<=', '==', '!=', '<', '>'
]

# Defines constant for use later.
LOG = None


class LoggerWriter(object):
    @property
    def fileno(self):
        return LOG.handlers[0].stream.fileno


def requirements_parse(pkgs, base_type='base_release'):
    """Parse all requirements.

    :param pkgs: ``list`` list of all requirements to parse.
    """
    for pkg in pkgs:
        LOG.debug('Parsing python dependencies: %s', pkg)
        if '==' in pkg:
            required_packages = PYTHON_PACKAGES['required_packages']
            pkg_name = '-'.join(pkg.split('=='))
            if pkg_name not in required_packages:
                required_packages[pkg_name] = pkg

        split_pkg = pkg.split(',')
        for version_descriptor in VERSION_DESCRIPTORS:
            if version_descriptor in split_pkg[0]:
                name, ver = split_pkg[0].split(version_descriptor)
                ver = '%s%s' % (version_descriptor, ver)
                if len(split_pkg) > 1:
                    versions = split_pkg[1:]
                    versions.insert(0, ver)
                else:
                    versions = [ver]

                break
        else:
            name = split_pkg[0]
            versions = None

        base_release = PYTHON_PACKAGES[base_type]
        if name in base_release:
            saved_versions = base_release[name]
            if versions is not None:
                if '==' in versions:
                    _lv = version.LooseVersion
                    if _lv(versions) < _lv(saved_versions):
                        versions = saved_versions
                        LOG.debug(
                            'New version found for replacement: [ %s ]',
                            versions
                        )

        if isinstance(versions, list):
            base_release[name.lower()] = '%s%s' % (name, ','.join(versions))
        elif versions is not None:
            base_release[name.lower()] = '%s%s' % (name, versions)
        else:
            base_release[name.lower()] = name


def package_dict(var_file):
    """Process variable file for Python requirements.

    :param var_file: ``str`` path to yaml file.
    """
    LOG.debug('Opening [ %s ]', var_file)
    with open(var_file, 'rb') as f:
        package_vars = yaml.safe_load(f.read())

    for pkgs in BUILT_IN_PIP_PACKAGE_VARS:
        pip_pkgs = package_vars.get(pkgs)
        if pip_pkgs and isinstance(pip_pkgs, list):
            requirements_parse(pkgs=pip_pkgs)

    git_repo = package_vars.get('git_repo')
    if git_repo:
        if git_repo not in GIT_REPOS:
            GIT_REPOS.append(git_repo)

        LOG.debug('Building git type package [ %s ]', git_repo)
        git_url = urlparse.urlsplit(git_repo)
        repo_name = os.path.basename(git_url.path)
        repo = PYTHON_PACKAGES['from_git'][repo_name] = {}
        repo['branch'] = package_vars.get('git_install_branch', 'master')
        repo['full_url'] = git_repo
        repo['project'] = repo_name

        setup_file = None
        for k, v in GIT_REQUIREMENTS_MAP.iteritems():
            if k in git_repo:
                for req_file in REQUIREMENTS_FILE_TYPES:
                    requirements_request = v % {
                        'path': git_url.path.lstrip('/'),
                        'file': req_file[1],
                        'branch': repo['branch']
                    }
                    req = requests.get(requirements_request)
                    LOG.debug(
                        'Return code [ %s ] while looking for [ %s ]',
                        req.status_code,
                        requirements_request
                    )
                    if req.status_code == 200:
                        LOG.debug(
                            'Found requirements [ %s ]', requirements_request
                        )
                        requirements = [
                            i.split()[0] for i in req.text.splitlines()
                            if i
                            if not i.startswith('#')
                        ]
                        repo[req_file[1].replace('-', '_')] = requirements
                        requirements_parse(
                            pkgs=requirements,
                            base_type=req_file[0]
                        )

                setup_request = v % {
                    'path': git_url.path.lstrip('/'),
                    'file': 'setup.py',
                    'branch': repo['branch']
                }
                setup = requests.head(setup_request)
                if setup.status_code == 200:
                    setup_file = True
                break

        git_req = 'git+%s@%s'
        known_release = PYTHON_PACKAGES['known_release']
        if setup_file is True:
            known_release[repo_name] = git_req % (
                repo['full_url'], repo['branch']
            )


def build_wheel(wheel_dir, build_dir, link_dir, dist=None, pkg_name=None,
                make_opts=None):
    """Execute python wheel build command.

    :param wheel_dir: ``str`` $PATH to local save directory
    :param build_dir: ``str`` $PATH to temp build directory
    :param dist: ``str`` $PATH to requirements file
    :param pkg_name: ``str`` name of package to build
    """
    command = [
        'pip',
        'wheel',
        '--find-links',
        link_dir,
        '--timeout',
        '120',
        '--wheel-dir',
        wheel_dir,
        '--allow-all-external',
        '--build',
        build_dir
    ]

    if make_opts is not None:
        for make_opt in make_opts:
            command.append(make_opt)

    if dist is not None:
        command.extend(['--requirement', dist])
    elif pkg_name is not None:
        command.append(pkg_name)
    else:
        raise SyntaxError('neither "dist" or "pkg_name" was specified')

    build_command = ' '.join(command)
    LOG.info('Command: %s' % build_command)
    output, unused_err = None, None
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=LoggerWriter()
        )
        output, unused_err = process.communicate()
        retcode = process.poll()

        LOG.info('Command return code: [ %s ]', retcode)
        if retcode:
            raise subprocess.CalledProcessError(
                retcode, build_command, output=output
            )
    except subprocess.CalledProcessError as exp:
        LOG.warn(
            'Process failure. stderr: [ %s ], stdout [ %s ], Exception'
            ' [ %s ]. Removing build directory for retry. Check log for'
            ' more details.',
            unused_err,
            output,
            str(exp)
        )
        remove_dirs(directory=build_dir)
    finally:
        # Ensure the build directories are clean
        remove_dirs(directory=build_dir)


def remove_dirs(directory):
    """Delete a directory recursively.

    :param directory: ``str`` $PATH to directory.
    """
    LOG.info('Removing directory [ %s ]', directory)
    for file_name in get_file_names(path=directory):
        LOG.debug('Removing file [ %s ]', file_name)
        os.remove(file_name)

    dir_names = []
    for dir_name, _, _ in os.walk(directory):
        dir_names.append(dir_name)

    dir_names = sorted(dir_names, reverse=True)
    for dir_name in dir_names:
        try:
            LOG.debug('Removing subdirectory [ %s ]', dir_name)
            os.removedirs(dir_name)
        except OSError:
            pass


def copy_file(src, dst):
    """Copy file from source to destination.

    :param src: ``str`` Path to source file.
    :param dst: ``str`` Path to destination file.
    """
    LOG.debug('Copying [ %s ] -> [ %s ]', src, dst)
    with open(src, 'rb') as open_src:
        with open(dst, 'wb') as open_dst:
            while True:
                buf = open_src.read(24 * 1024)
                if not buf:
                    break
                else:
                    open_dst.write(buf)


def _requirements_maker(name, wheel_dir, release, build_dir, make_opts,
                        link_dir=None, iterate=False):
    """Parse lists of requirements.

    :param name: ``str`` name of requirements file.
    :param wheel_dir: ``str`` Path to store wheels.
    :param release: ``str`` release branch name.
    :param build_dir: ``str`` Path to build location.
    :param make_opts: ``list`` List of string options to use when building.
    :param link_dir: ``Path to link location.
    :param iterate: ``bol`` Iterate through the list of requirements.
    """
    if link_dir is None:
        link_dir = wheel_dir

    if iterate is True:
        for pkg in sorted(release.values()):
            build_wheel(
                wheel_dir=wheel_dir,
                build_dir=build_dir,
                link_dir=link_dir,
                pkg_name=pkg,
                make_opts=make_opts
            )
    else:
        requirements_file_lines = []
        for value in sorted(set(release.values())):
            requirements_file_lines.append('%s\n' % value)

        requirements_file = os.path.join(wheel_dir, name)
        with open(requirements_file, 'wb') as f:
            f.writelines(requirements_file_lines)

        build_wheel(
            wheel_dir=wheel_dir,
            build_dir=build_dir,
            link_dir=link_dir,
            dist=requirements_file,
            make_opts=make_opts
        )


def _make_wheels(wheel_dir, build_dir, temp_store_dir):
    """Build all of the python wheels.

    :param wheel_dir: ``str`` Path to store wheels.
    :param build_dir: ``str`` Path to build location.
    :param temp_store_dir: ``str`` Path to temp directory.
    """
    LOG.info('Building base packages')
    _requirements_maker(
        name='opc_base_requirements.txt',
        wheel_dir=temp_store_dir,
        release=PYTHON_PACKAGES['base_release'],
        build_dir=build_dir,
        make_opts=None,
        link_dir=wheel_dir
    )

    LOG.info('Building test packages')
    _requirements_maker(
        name='opc_test_requirements.txt',
        wheel_dir=temp_store_dir,
        release=PYTHON_PACKAGES['test_requirements'],
        build_dir=build_dir,
        make_opts=None,
        link_dir=wheel_dir
    )

    LOG.info('Building known absolute packages')
    _requirements_maker(
        name='opc_known_requirements.txt',
        wheel_dir=temp_store_dir,
        release=PYTHON_PACKAGES['known_release'],
        build_dir=build_dir,
        make_opts=['--no-deps'],
        link_dir=wheel_dir
    )

    LOG.info('Building required packages')
    _requirements_maker(
        name='opc_required_requirements.txt',
        wheel_dir=temp_store_dir,
        release=PYTHON_PACKAGES['required_packages'],
        build_dir=build_dir,
        make_opts=None,
        link_dir=wheel_dir,
        iterate=True
    )

    # Get all of the file names
    built_wheels = get_file_names(temp_store_dir)

    # Sort the files and ensure we don't index *.txt files.
    built_wheels = sorted([i for i in built_wheels if not i.endswith('.txt')])

    try:
        with open('/opt/repo-blacklist.txt', 'rb') as f:
            blacklist = [i.strip() for i in f.readlines() if i.strip()]
    except IOError:
        blacklist = list()

    # Filter the built wheel items for anything that is a known blacklist
    built_wheels = [i for i in built_wheels for t in blacklist if t not in i]
    LOG.debug('Built wheels: %s', built_wheels)

    PYTHON_PACKAGES['built_files'] = [
        os.path.basename(i) for i in built_wheels
    ]

    LOG.info('Moving built packages into place')
    for built_wheel in built_wheels:
        wheel_file = os.path.join(wheel_dir, os.path.basename(built_wheel))
        if os.path.exists(wheel_file):
            if os.path.getsize(wheel_file) != os.path.getsize(built_wheel):
                copy_file(src=built_wheel, dst=wheel_file)
        else:
            copy_file(src=built_wheel, dst=wheel_file)


def make_wheels(wheel_dir, build_dir):
    """Build wheels of all installed packages that don't already have one.

    :param wheel_dir: ``str`` $PATH to local save directory
    :param build_dir: ``str`` $PATH to temp build directory
    """

    temp_store_dir = os.path.join(
        tempfile.mkdtemp(prefix='opc_wheels_temp_storage')
    )
    _mkdirs(path=temp_store_dir)
    try:
        _make_wheels(
            wheel_dir=wheel_dir,
            build_dir=build_dir,
            temp_store_dir=temp_store_dir
        )
    finally:
        remove_dirs(directory=temp_store_dir)
        remove_dirs(
            directory=os.path.join(
                tempfile.gettempdir(),
                'pip_build_root'
            )
        )


def ensure_consistency():
    """Iterate through the known data set and remove duplicates."""

    LOG.info('Ensuring the package list is consistent')
    for key in PYTHON_PACKAGES['known_release'].keys():
        for release in ['test_requirements', 'base_release']:
            PYTHON_PACKAGES[release].pop(key, None)


def get_file_names(path, ext=None):
    """Return a list of all files in the vars/repo_packages directory.

    :param path: ``str``  $PATH to search for files
    :param ext: ``str`` or ``tuple``  extension filter for specific files.
    """

    paths = os.walk(os.path.abspath(path))
    files = list()
    for fpath, _, afiles in paths:
        basename = os.path.basename(fpath)
        if not basename == 'defaults' and not '/vars' in fpath:
            continue

        for afile in afiles:
            if ext is not None:
                if afile.endswith(ext):
                    files.append(os.path.join(fpath, afile))
            else:
                files.append(os.path.join(fpath, afile))
    else:
        return files


def _error_handler(msg, system_exit=True):
    """Handle and error logging and exit the application if needed.

    :param msg: ``str`` message to log
    :param system_exit: ``bol`` if true the system will exit with an error.
    """
    LOG.error(msg)
    if system_exit is True:
        raise SystemExit(msg)


def _user_args():
    """Setup argument Parsing."""

    parser = argparse.ArgumentParser(
        usage='%(prog)s',
        description='Rackspace Openstack, Python wheel builder',
        epilog='Python package builder Licensed "Apache 2.0"'
    )
    file_input = parser.add_mutually_exclusive_group(required=True)
    file_input.add_argument(
        '-i',
        '--input',
        help='Path to the directory where the repo_packages/ file or filess'
             ' are. This can be set to a directory or a file. If the path is'
             ' a directory all .yml files will be scanned for python packages'
             ' and git repositories.',
        default=None
    )
    file_input.add_argument(
        '--pre-input',
        help='Path to a already built json file which contains the python'
             ' packages and git repositories required.',
        default=None
    )
    parser.add_argument(
        '-o',
        '--output',
        help='Path to the location where the built Python package files will'
             ' be stored.',
        required=True,
        default=None
    )
    parser.add_argument(
        '-g',
        '--git-repos',
        help='Path to where to store all of the git repositories.',
        required=False,
        default=None
    )
    parser.add_argument(
        '--build-dir',
        help='Path to temporary build directory. If unset a auto generated'
             ' temporary directory will be used.',
        required=False,
        default=None
    )
    parser.add_argument(
        '--link-dir',
        help='Path to the build links for all built wheels.',
        required=False,
        default=None
    )
    parser.add_argument(
        '-r',
        '--release',
        help='Name of the release. Used for generating the json report.',
        required=True,
        default=None
    )
    opts = parser.add_mutually_exclusive_group()
    opts.add_argument(
        '--debug',
        help='Enable debug mode',
        action='store_true',
        default=False
    )
    opts.add_argument(
        '--quiet',
        help='Enables quiet mode, this disables all stdout',
        action='store_true',
        default=False
    )

    return vars(parser.parse_args())


def _get_abs_path(path):
    """Return the absolute path for a given path.

    :param path: ``str``  $PATH to be created
    :returns: ``str``
    """
    return os.path.abspath(
        os.path.expanduser(
            path
        )
    )


def _mkdirs(path):
    """Create a directory.

    :param path: ``str``  $PATH to be created
    """
    if not os.path.exists(path):
        LOG.info('Creating directory [ %s ]' % path)
        os.makedirs(path)
    else:
        if not os.path.isdir(path):
            error = (
                'Path [ %s ] can not be created, it exists and is not already'
                ' a directory.' % path
            )
            _error_handler(msg=error)


def _store_git_repos(git_repos_path):
    """Clone and or update all git repos.

    :param git_repos_path: ``str`` Path to where to store the git repos
    """
    _mkdirs(git_repos_path)
    for git_repo in GIT_REPOS:
        repo_name = os.path.basename(git_repo)
        if repo_name.endswith('.git'):
            repo_name = repo_name.rstrip('git')

        repo_path_name = os.path.join(git_repos_path, repo_name)
        if os.path.isdir(repo_path_name):
            os.chdir(repo_path_name)
            LOG.debug('Updating git repo [ %s ]', repo_path_name)
            commands = [
                ['git', 'fetch', '-p', 'origin'],
                ['git', 'pull']
            ]
        else:
            LOG.debug('Cloning into git repo [ %s ]', repo_path_name)
            commands = [
                ['git', 'clone', git_repo, repo_path_name]
            ]

        for command in commands:
            try:
                ret_data = subprocess.check_call(
                    command,
                    stdout=LoggerWriter(),
                    stderr=LoggerWriter()
                )
                if ret_data:
                    raise subprocess.CalledProcessError(
                        ret_data, command
                    )
            except subprocess.CalledProcessError as exp:
                LOG.warn('Process failure. Error: [ %s ]', str(exp))
            else:
                LOG.debug('Command return code: [ %s ]', ret_data)


class DependencyFileProcessor(object):
    def __init__(self, local_path='/opt/os-ansible-deployment', ext=None):
        if not ext:
            ext = ('yaml', 'yml')

        self.dependencies = dict()
        self.pip = list()
        self.file_names = self._get_files(path=local_path, ext=ext)

        # Process everything simply by calling the class
        self._process_files()

    @staticmethod
    def _get_files(path, ext=None):
        """Return a list of all files in the vars/repo_packages directory.

        :param path: ``str``  $PATH to search for files
        :param ext: ``str`` or ``tuple``  extension filter for specific files.
        """

        paths = os.walk(os.path.abspath(path))
        files = list()
        for fpath, _, afiles in paths:
            basename = os.path.basename(fpath)
            if not basename == 'defaults' and not '/vars' in fpath:
                continue

            for afile in afiles:
                if ext is not None:
                    if afile.endswith(ext):
                        files.append(os.path.join(fpath, afile))
                else:
                    files.append(os.path.join(fpath, afile))
        else:
            return files

    @staticmethod
    def _check_requirements(requirements_path):
        req = requests.get(requirements_path)
        LOG.debug(
            'Return code [ %s ] while looking for [ %s ]',
            req.status_code,
            requirements_path
        )
        if req.status_code == 200:
            LOG.debug(
                'Found requirements [ %s ]', requirements_path
            )
            return [
                i.split()[0] for i in req.text.splitlines()
                if i
                if not i.startswith('#')
            ]

    @staticmethod
    def _check_plugins(git_repo_plugins, git_data):
        plugin_data = dict()
        for repo_plugin in git_repo_plugins:
            plugin = '%s/%s' % (
                repo_plugin['path'].strip('/'),
                repo_plugin['package'].lstrip('/')
            )
            plugin_data[repo_plugin['package']] = 'git+%s@%s' % (
                git_data['full_url'],
                '%s#egg=%s&subdirectory=%s' % (
                    git_data['branch'],
                    repo_plugin['package'].strip('/'),
                    plugin
                )
            )
        else:
            return plugin_data

    @staticmethod
    def _check_setup(setup_path, git_data):
        req = requests.head(setup_path)
        if req.status_code == 200:
            return 'git+%(full_url)s@%(branch)s' % git_data

    def _process_git(self, loaded_yaml, git_item):
        git_url = os.path.splitext(loaded_yaml[git_item])[0]
        git_url = urlparse.urlsplit(git_url)
        repo_name = os.path.basename(git_url.path)
        git_data = self.dependencies[repo_name] = dict()
        git_data['full_url'] = git_url.geturl()
        git_data['path'] = git_url.path.strip('/')
        git_data['project'] = repo_name
        git_data['py_from_git'] = dict()
        if git_item.split('_')[0] == 'git':
            var_name = 'git'
        else:
            var_name = git_item.split('_')[0]

        git_data['branch'] = loaded_yaml.get(
            '%s_git_install_branch' % var_name,
            'master'
        )
        git_repo_plugins = loaded_yaml.get('%s_repo_plugins' % var_name)
        if git_repo_plugins:
            git_data['py_from_git'].update(
                self._check_plugins(
                    git_repo_plugins=git_repo_plugins,
                    git_data=git_data
                )
            )

        py_reqs = dict()
        for k, v in GIT_REQUIREMENTS_MAP.items():
            if k in git_data['full_url']:
                _git_data = git_data.copy()
                for req_type, req_file in REQUIREMENTS_FILE_TYPES:
                    _git_data['file'] = req_file
                    request_path = v % _git_data
                    requirements = self._check_requirements(
                        requirements_path=request_path
                    )
                    if requirements:
                        py_reqs[req_file] = requirements
                        requirements_parse(
                            pkgs=requirements,
                            base_type=req_type
                        )

                _git_data['file'] = 'setup.py'
                setup_path = v % _git_data
                setup_py = self._check_setup(
                    setup_path=setup_path,
                    git_data=_git_data
                )
                if setup_py:
                    git_data['py_from_git'].update({'main': setup_py})

        if py_reqs:
            git_data['requirements_files'] = py_reqs

    def _process_files(self):
        for file_name in self.file_names:
            with open(file_name, 'rb') as f:
                loaded_config = yaml.safe_load(f.read())

            git_items = list()
            for key, value in loaded_config.items():
                if key.endswith('git_repo'):
                    git_items.append(key)

                if key.endswith(tuple(BUILT_IN_PIP_PACKAGE_VARS)):
                    self.pip.extend(value)
            else:
                for item in git_items:
                    self._process_git(
                        loaded_yaml=loaded_config,
                        git_item=item
                    )
        else:
            self.dependencies['pip_packages'] = list(set(self.pip))


def pre_load_logging(user_args):
    # Load the logging
    _logging = logger.LogSetup(debug_logging=user_args['debug'])
    if user_args['quiet'] is True or user_args['debug'] is False:
        spinner = stream = False
    else:
        spinner = stream = True

    _logging.default_logger(name='opc_wheel_builder', enable_stream=stream)

    global LOG
    LOG = logger.getLogger(name='opc_wheel_builder')
    return spinner


def main():
    """Run the main app.

    This application will create all Python wheel files from within an
    environment.  The purpose is to create pre-compiled python wheels from
    the RPC playbooks.
    """

    # Parse input arguments
    user_args = _user_args()
    if not os.path.isdir(user_args['input']):
        raise SystemExit('Input path is not a directory.')

    # Load the logging options
    spinner = pre_load_logging(user_args)

    # Gather dependencies
    indicator_kwargs = {'run': spinner, 'msg': 'Gather dependencies... '}
    with indicator.Spinner(**indicator_kwargs):
        deps = DependencyFileProcessor(local_path=user_args['input'])

    # Create the output path
    output_path = _get_abs_path(path=user_args['output'])
    LOG.info('Getting output path')
    _mkdirs(path=output_path)

    # Create the build path
    LOG.info('Getting build path')
    if user_args['build_dir'] is not None:
        build_path = _get_abs_path(path=user_args['build_dir'])
        _mkdirs(path=build_path)
    else:
        build_path = tempfile.mkdtemp(prefix='opc_wheels_build_')

    indicator_kwargs['msg'] = 'Building wheels... '
    with indicator.Spinner(**indicator_kwargs):
        # Create all of the python package wheels
        make_wheels(
            wheel_dir=output_path,
            build_dir=build_path
        )

    indicator_kwargs['msg'] = 'Generating build log... '
    with indicator.Spinner(**indicator_kwargs):
        # Get a timestamp and create a report file
        utctime = datetime.datetime.utcnow()
        utctime = utctime.strftime("%Y%m%d_%H%M%S")
        backup_name = '%s-build-report-%s.json' % (
            user_args['release'],
            utctime
        )
        output_report_file = os.path.join(
            output_path,
            'json-reports',
            backup_name
        )

        # Make the directory if needed
        _mkdirs(path=os.path.dirname(output_report_file))

        # Generate a timestamped report file
        LOG.info('Generating packaging report [ %s ]', output_report_file)
        with open(output_report_file, 'wb') as f:
            f.write(
                json.dumps(
                    PYTHON_PACKAGES,
                    indent=2,
                    sort_keys=True
                )
            )

    # If link_dir is defined create a link to all built wheels.
    links_path = user_args.get('link_dir')
    if links_path:
        indicator_kwargs['msg'] = 'Creating file links... '
        with indicator.Spinner(**indicator_kwargs):
            links_path = _get_abs_path(path=links_path)
            LOG.info('Creating Links at [ %s ]', links_path)
            _mkdirs(path=links_path)

            # Change working directory.
            os.chdir(links_path)

            # Create all the links
            for inode in PYTHON_PACKAGES['built_files']:
                try:
                    dest_link = os.path.join(links_path, inode)

                    # Remove the destination inode if it exists
                    if os.path.exists(dest_link):
                        os.remove(dest_link)

                    # Create the link using the relative path
                    os.symlink(os.path.relpath(
                        os.path.join(output_path, inode)), dest_link
                    )
                except OSError as exp:
                    LOG.warn(
                        'Error Creating Link: [ %s ] Error: [ %s ]',
                        inode,
                        exp
                    )
                else:
                    LOG.debug('Link Created: [ %s ]', dest_link)

    # if git_repos was defined save all of the sources to the defined location
    git_repos_path = user_args.get('git_repos')
    if git_repos_path:
        indicator_kwargs['msg'] = 'Storing updated git sources...'
        with indicator.Spinner(**indicator_kwargs):
            LOG.info('Updating git sources [ %s ]', links_path)
            _store_git_repos(_get_abs_path(path=git_repos_path))


if __name__ == "__main__":
    main()
