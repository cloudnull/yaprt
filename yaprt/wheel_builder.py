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

import collections
import os
import tempfile
from distutils import version

from cloudlib import logger
from cloudlib import shell

from yaprt import utils


LOG = logger.getLogger('repo_builder')
VERSION_DESCRIPTORS = ['>=', '<=', '==', '<', '>', '!=']


class WheelBuilder(object):
    def __init__(self, user_args):
        self.args = user_args
        self.shell_cmds = shell.ShellCommands(
            log_name='repo_builder',
            debug=self.args['debug']
        )
        self.branches = list()
        self.requirements = list()
        self.releases = list()

    def _build_wheels(self, package):
        command = [
            'pip',
            'wheel',
            '--timeout',
            '120',
            '--wheel-dir',
            self.args['build_output'],
            '--allow-all-external'
        ]

        if self.args['pip_no_deps']:
            command.extend(['--no-deps'])

        if self.args['pip_no_index']:
            command.extend(['--no-index'])

        if self.args['build_dir']:
            build_dir = self.args['build_dir']
            command.extend(['--build', build_dir])
        else:
            build_dir = tempfile.mkstemp(prefix='orb_')
            command.extend(['--build', build_dir])

        # Add the output wheel directory as a link source
        command.extend(['--find-links', self.args['build_output']])

        if self.args['link_dir']:
            command.extend(['--find-links', self.args['link_dir']])

        if self.args['pip_extra_link_dirs']:
            for link in self.args['pip_extra_link_dirs']:
                command.extend(['--find-links', link])

        if self.args['pip_index']:
            command.extend(['--index-url', self.args['pip_index']])

        if self.args['pip_extra_index']:
            command.extend(['--extra-index-url', self.args['pip_extra_index']])

        if self.args['debug'] is True:
            command.append('--verbose')

        command.append('"%s"' % package)
        try:
            stdout, success = self.shell_cmds.run_command(
                command=' '.join(command)
            )
            if not success:
                raise OSError(stdout)
        except OSError as exp:
            LOG.error('Failed to process wheel build: %s', str(exp))
        finally:
            utils.remove_dirs(directory=build_dir)

    @staticmethod
    def version_compare(versions, duplicate_handling='max'):
        versions.sort(key=version.LooseVersion)
        if duplicate_handling == 'max':
            return versions[-1]
        elif duplicate_handling == 'min':
            return versions[0]
        else:
            versions.reverse()
            return versions

    @staticmethod
    def _requirement_name(requirement):
        for version_descriptor in VERSION_DESCRIPTORS:
            if version_descriptor in requirement:
                name = requirement.split(version_descriptor)[0]
                versions = requirement.split(name)[-1].split(',')
                return name, versions
        else:
            return requirement, list()

    def _sort_requirements(self):
        _requirements = dict()
        for requirement in list(set(self.requirements)):
            name, versions = self._requirement_name(requirement)
            if name in _requirements:
                req = _requirements[name]
            else:
                req = _requirements[name] = list()

            req.extend(versions)

        packages = list()
        for pkg_name, versions in _requirements.items():
            vds = dict([(i, list()) for i in VERSION_DESCRIPTORS])
            q = collections.deque(list(set(versions)))
            while q:
                _version = q.pop()
                for version_descriptor in vds.keys():
                    if version_descriptor in _version:
                        content = _version.split(version_descriptor)[-1]
                        vds[version_descriptor].append(content)
                        break

            for key, value in vds.items():
                value = list(set(value))
                if value and key != '!=':
                    vds[key] = self.version_compare(
                        versions=value,
                        duplicate_handling=self.args['duplicate_handling']
                    )
                elif value and key == '!=':
                    vds[key] = self.version_compare(
                        versions=value,
                        duplicate_handling='not_equal'
                    )
                else:
                    vds[key] = list()

            if vds['==']:
                packages.append('%s==%s' % (pkg_name, vds['==']))
            else:
                _versions = list()
                for vd in VERSION_DESCRIPTORS:
                    if vds[vd] and isinstance(vds[vd], basestring):
                        _versions.append('%s%s' % (vd, vds[vd]))
                    elif vds[vd] and isinstance(vds[vd], list):
                        _versions.extend(['%s%s' % (vd, i) for i in vds[vd]])
                else:
                    if _versions:
                        packages.append(
                            '%s%s' % (pkg_name, ','.join(_versions))
                        )
                    else:
                        packages.append(pkg_name)

        return sorted(packages)

    def _pop_items(self, found_repos, list_items):
        item_list = getattr(self, list_items)
        for found_repo in found_repos:
            idx = item_list.index(found_repo)
            item_list.pop(idx)

    def _pop_requirements(self, release):
        name = utils.git_pip_link_parse(repo=release)[0]
        self._pop_items(
            found_repos=[
                i for i in self.requirements
                if self._requirement_name(i)[0] == name
            ],
            list_items='requirements'
        )

    def _pop_branches(self, release):
        name = utils.git_pip_link_parse(repo=release)[0]
        self._pop_items(
            found_repos=[
                i for i in self.branches
                if utils.git_pip_link_parse(repo=i)[0] == name
            ],
            list_items='branches'
        )

    def get_requirements(self, report):
        for repo in report.values():
            for repo_branch in repo['branches'].values():
                if repo_branch.get('requirements'):
                    for key, value in repo_branch['requirements'].items():
                        self.requirements.extend(value)
        else:
            self.requirements = self._sort_requirements()

    def get_branches(self, report):
        for repo in report.values():
            for repo_branch in repo['branches'].values():
                if repo_branch.get('pip_install_url'):
                    release = repo_branch['pip_install_url']
                    self.branches.append(release)
                    self._pop_requirements(release)
        else:
            self.branches = sorted(list(set(self.branches)))

    def get_releases(self, report):
        for repo in report.values():
            if 'releases' in repo and isinstance(repo['releases'], list):
                self.releases.extend(repo['releases'])
                for release in repo['releases']:
                    self._pop_requirements(release)
                    self._pop_branches(release)
        else:
            self.releases = sorted(list(set(self.releases)))

    def _copy_file(self, dst_file, src_file):
        ## TODO(kevin)  This should be uncommented to provide a hash on the
        ## TODO(kevin)  filename, but NGINX escapes "#sha256=" as
        ## TODO(kevin)  "%23sha256%3d" and that makes the browser/pip angry
        # hash_type = 'sha256'
        # dst_file = '%(name)s%(break)s%(type)s%(equal)s%(hash)s' % {
        #     'name': dst_file,
        #     'break': '#',
        #     'type': hash_type,
        #     'equal': '=',
        #     'hash': utils.hash_return(
        #         local_file=src_file,
        #         hash_type=hash_type
        #     )
        # }

        utils.copy_file(src=src_file, dst=dst_file)

    def _store_pool(self):
        built_wheels = utils.get_file_names(
            path=self.args['build_output']
        )

        # Iterate through the built wheels
        for built_wheel in built_wheels:
            _dst_wheel_file_name = os.path.basename(built_wheel)
            dst_wheel_file = os.path.join(
                self.args['storage_pool'],
                _dst_wheel_file_name.split('-')[0],
                _dst_wheel_file_name
            )

            # Ensure the directory exists
            self.shell_cmds.mkdir_p(path=os.path.dirname(dst_wheel_file))

            # Create destination file
            if os.path.exists(dst_wheel_file):
                dst_size = os.path.getsize(dst_wheel_file)
                src_size = os.path.getsize(built_wheel)
                if dst_size != src_size:
                    self._copy_file(
                        dst_file=dst_wheel_file,
                        src_file=built_wheel
                    )
            else:
                self._copy_file(
                    dst_file=dst_wheel_file,
                    src_file=built_wheel
                )

            # Create link
            if self.args['link_dir']:
                self._create_link(
                    full_wheel_path=dst_wheel_file,
                    wheel_name=os.path.basename(dst_wheel_file)
                )

    def _create_link(self, full_wheel_path, wheel_name):
        with utils.ChangeDir(self.args['link_dir']):
            # Create the link using the relative path
            link_path = os.path.join(self.args['link_dir'], wheel_name)
            try:
                # If the link is broken remove it
                if not os.path.exists(os.readlink(link_path)):
                    os.remove(link_path)
            except OSError as exp:
                if exp.errno == 2:
                    pass
                else:
                    raise exp

            if not os.path.islink(link_path):
                # Create the symlink
                os.symlink(
                    os.path.relpath(full_wheel_path),
                    os.path.join(self.args['link_dir'], wheel_name)
                )

    def build_wheels(self, packages, log_build=False):
        try:
            for package in packages:
                self._build_wheels(package=package)
            else:
                self._store_pool()
        finally:
            utils.remove_dirs(directory=self.args['build_output'])
