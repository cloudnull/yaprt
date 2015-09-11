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
# (c) 2015, Kevin Carter <kevin.carter@rackspace.com>

import collections
from distutils import version
import os
import re
import tempfile
import urlparse

from cloudlib import logger

from yaprt import utils


LOG = logger.getLogger('repo_builder')
VERSION_DESCRIPTORS = ['>=', '<=', '>', '<', '==', '~=', '!=']


def build_wheels(args):
    """Work through the various wheels based on arguments.

    :param args: User defined arguments.
    :type args: ``dict``
    """
    report = utils.read_report(args=args)
    wb = WheelBuilder(user_args=args)

    # Everything is built in order for consistency, even if it's not being
    # used later.
    wb.get_requirements(report=report)
    wb.get_branches(report=report)
    wb.get_releases(report=report)

    packages = list()
    if args['build_packages']:
        LOG.info('Building select packages: %d', len(args['build_packages']))
        # Build a given set of wheels as hard requirements.
        wb.build_wheels(
            packages=wb.sort_requirements(
                requirements_list=args['build_packages']
            )
        )
        wb.requirements.extend(args['build_packages'])
        wb.requirements = list(set(wb.requirements))

    if args['build_requirements']:
        LOG.info('Found requirements: %d', len(wb.requirements))

        # Make sure that the pip package is built first, if its included.
        for item in wb.requirements:
            if item.startswith('pip'):
                wb.requirements.insert(
                    0, wb.requirements.pop(
                        wb.requirements.index(
                            item
                        )
                    )
                )
            # TODO(cloudnull) Remove this when httpretty sucks less.
            elif item.startswith('httpretty'):
                LOG.warn(
                    'httpretty is an awful package and is generally'
                    ' un-buildable. Please use something else if possible.'
                    ' The package install for httpretty is being changed to'
                    ' "httpretty>=0.8.3" as its really the only functional'
                    ' version of this package that has been released.'
                )
                wb.requirements.pop(
                    wb.requirements.index(
                        item
                    )
                )
                wb.requirements.append('httpretty>=0.8.3')
        packages.extend(wb.requirements)

    wb.build_wheels(
        packages=packages,
        clean_first=args['force_clean']
    )

    if args['build_branches']:
        LOG.info('Found branch packages: %d', len(wb.branches))
        wb.build_wheels(
            packages=wb.branches,
            clean_first=args['force_clean'],
            force_iterate=True
        )

    if args['build_releases']:
        LOG.info('Found releases: %d', len(wb.releases))
        wb.build_wheels(
            packages=wb.releases,
            clean_first=args['force_clean'],
            force_iterate=True
        )


class WheelBuilder(utils.RepoBaseClass):
    """Build python wheel files.

    Example options dict
        >>> user_args = {
        ...     'build_output': '/tmp/output_place',
        ...     'build_dir': '/tmp/build_place',
        ...     'pip_no_deps': True,
        ...     'pip_no_index': True,
        ...     'pip_pre': False,
        ...     'link_dir': '/var/www/repo',
        ...     'debug': True,
        ...     'duplicate_handling': 'max',
        ...     'storage_pool': '/var/www/repo/storage'
        ... }
    """
    def __init__(self, user_args):
        """Build python wheels based on a report or items within a report.

        :param user_args: User defined arguments.
        :type user_args: ``dict``
        :return:
        """
        super(WheelBuilder, self).__init__(
            user_args=user_args,
            log_object=LOG
        )

        self.branches = list()
        self.requirements = list()
        self.releases = list()

    @staticmethod
    def version_compare(versions, duplicate_handling='max'):
        """Return a list of sorted versions.

        :param versions: List of versions.
        :type versions: ``list``
        :param duplicate_handling: How to handle an issue with duplicate
                                   versions within a versions list.
        :type duplicate_handling: ``str``
        :returns: ``list`` or ``str``
        """
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
        """Return a ``tuple`` of requirement name and list of versions.

        :param requirement: Name of a requirement that may have versions within
                            it. This will use the constant,
                            VERSION_DESCRIPTORS.
        :type requirement: ``str``
        :return: ``tuple``
        """
        check_addon_markers = requirement.split(';')
        if len(check_addon_markers) > 1:
            markers = check_addon_markers[1]
            requirement = check_addon_markers[0]
        else:
            markers = None

        name = re.split(r'%s\s*' % VERSION_DESCRIPTORS, requirement)[0]
        versions = requirement.split(name)

        if len(versions) < 1:
            versions = list()
        else:
            versions = versions[-1].split(',')
        return name, versions, markers

    @staticmethod
    def _copy_file(dst_file, src_file):
        """Copy a source file to a destination file.

        :param dst_file: Destination file.
        :type dst_file: ``str``
        :param src_file: Source file.
        :type src_file: ``str``
        """
        utils.copy_file(src=src_file, dst=dst_file)

    def _pip_build_wheels(self, package=None, packages_file=None,
                          no_links=False, retry=False):
        """Create a python wheel.

        The base command will timeout in 120 seconds and will create the wheels
        within a defined build output directory, will allow external packages,
        and will source the build output directory as the first link directory
        to look through for already build wheels.

        the argument options will enable no dependencies build, setting a build
        directory otherwise a temporary directory will be used, setting an
        additional link directory, setting extra link directories, changing the
        defaul pip index URL, adding an extra pip index URL, and enabling
        verbose mode.

        :param package: Name of a particular package to build.
        :type package: ``str``
        :param packages_file: $PATH to the file which contains a list of
                              packages to build.
        :type packages_file: ``str``
        :param no_links: Enable / Disable add on links when building the wheel.
        :type no_links: ``bol``
        :param retry: Enable retry mode.
        :type retry: ``bol``
        """
        command = [
            'pip',
            'wheel',
            '--timeout',
            '120',
            '--wheel-dir',
            self.args['build_output'],
            '--allow-all-external'
        ]

        if self.args['pip_pre']:
            command.append('--pre')

        if not no_links:
            if self.args['pip_extra_link_dirs']:
                for link in self.args['pip_extra_link_dirs']:
                    command.extend(['--find-links', link])

        if self.args['pip_no_deps']:
            command.append('--no-deps')
        else:
            if self.args['pip_index']:
                command.extend(['--index-url', self.args['pip_index']])
                domain = urlparse.urlparse(self.args['pip_index'])
                command.extend(['--trusted-host', domain.hostname])

            if self.args['pip_extra_index']:
                command.extend(
                    ['--extra-index-url', self.args['pip_extra_index']]
                )
                domain = urlparse.urlparse(self.args['pip_extra_index'])
                command.extend(['--trusted-host', domain.hostname])

        if self.args['pip_no_index']:
            command.append('--no-index')

        if self.args['build_dir']:
            build_dir = self.args['build_dir']
            command.extend(['--build', build_dir])
        else:
            build_dir = tempfile.mkstemp(prefix='orb_')
            command.extend(['--build', build_dir])

        if self.args['debug'] is True:
            command.append('--verbose')

        if packages_file:
            command.extend(['--requirement', packages_file])
        else:
            command.append('"%s"' % utils.stip_quotes(item=package))
        try:
            self._run_command(command=command)
        except (IOError, OSError) as exp:
            # If retry mode is enabled and there's an exception fail
            if retry:
                raise utils.AError(
                    'Failed to process wheel build: "%s", other data: "%s"',
                    package or packages_file,
                    str(exp)
                )

            LOG.warn(
                'Failed to process wheel build: "%s", other data: "%s"'
                ' Trying again without defined link lookups.',
                package or packages_file,
                str(exp)
            )

            # Remove the build directory when failed.
            utils.remove_dirs(build_dir)

            # Rerun wheel builder in retry mode without links
            build_wheel_args = {'no_links': True, 'retry': True}
            if package:
                build_wheel_args['package'] = package
            else:
                build_wheel_args['packages_file'] = packages_file
            self._pip_build_wheels(**build_wheel_args)
        else:
            LOG.debug('Build Success for: "%s"', package or packages_file)
        finally:
            utils.remove_dirs(directory=build_dir)

    def _setup_build_wheels(self, package):
        """Create a Python wheel using a git with subdirectories.

        The method will clone the source into place, move to the designated
        sub directory and create a python wheel from the designated
        subdirectory.

        :param package: Name of a particular package to build.
        :type package: ``str``
        """
        package_full_link = package.split('git+')[1]

        if '#' in package_full_link:
            package_link, extra_data = package_full_link.split('#')
        else:
            package_link, extra_data = package_full_link, None

        package_link, branch = package_link.split('@')

        # Split the branches to see if there are multiple checkouts/branches
        git_branches, int_branch = self.split_git_branches(git_branch=branch)
        if len(git_branches) > 1 or 'refs/changes' in branch:
            branch = int_branch

        package_name = utils.git_pip_link_parse(repo=package)[0]
        repo_location = os.path.join(
            self.args['git_repo_path'], package_name
        )
        if extra_data and 'subdirectory' in extra_data:
            package_subdir = extra_data.split('subdirectory=')[1].split('&')[0]
            git_package_location = os.path.join(
                repo_location,
                package_subdir
            )
        else:
            git_package_location = repo_location

        # Check that setuptools is available
        setup_py = 'setup.py'
        setup_file = os.path.join(git_package_location, setup_py)
        remove_extra_setup = False
        if os.path.isfile(setup_file):
            with open(setup_file, 'r') as f:
                setup_file_contents = [
                    i for i in f.readlines() if i if not i.startswith('#')
                ]
                for i in setup_file_contents:
                    if 'setuptools' in i:
                        break
                else:
                    for line in setup_file_contents:
                        if line.startswith('import'):
                            pass
                        elif line.startswith('from'):
                            pass
                        else:
                            index = setup_file_contents.index(line)
                            break
                    else:
                        index = 0

                    setup_file_contents.insert(index, 'import setuptools')
                    setup_py = '%s2' % setup_file
                    remove_extra_setup = True
                    with open(setup_py, 'w') as sf:
                        sf.writelines(setup_file_contents)
        try:
            with utils.ChangeDir(git_package_location):
                # Checkout the given branch
                checkout_command = ['git', 'checkout', "'%s'" % branch]
                self._run_command(command=checkout_command)

                # Build the wheel using `python setup.py`
                build_command = [
                    'python',
                    setup_py,
                    'bdist_wheel',
                    '--dist-dir',
                    self.args['build_output'],
                    '--bdist-dir',
                    self.args['build_dir']
                ]
                self._run_command(command=build_command)
            LOG.debug('Build Success for: "%s"', package)
        finally:
            utils.remove_dirs(directory=self.args['build_dir'])
            if remove_extra_setup:
                os.remove(setup_py)

    @staticmethod
    def _get_sentinel(operators, vds):
        """Return a sentinel and operator value.

        :param operators: List of operators.
        :type operators: ``list``
        :param vds: Package version descriptors.
        :type vds: ``dict``
        :returns: ``tuple``
        """
        for operator in operators:
            version_value = vds.get(operator, None)
            if version_value:
                return version_value, operator
        else:
            return None, None

    def _version_sanity_check(self, vds, pkg_name, duplicate_handling='max'):
        """Perform version description sanity check.

        :param vds: Package version descriptors.
        :type vds: ``dict``
        :return: ``dict``
        """
        if duplicate_handling == 'max':
            sentinel, anchor = self._get_sentinel(
                operators=['>=', '>'],
                vds=vds
            )
        elif duplicate_handling == 'min':
            sentinel, anchor = self._get_sentinel(
                operators=['<=', '<'],
                vds=vds
            )
        else:
            # if the `duplicate_handling` is not "min" or "max" return vds.
            return vds

        # When no sentinel was set return vds.
        if not sentinel:
            return vds

        vlv = version.LooseVersion
        for vd in VERSION_DESCRIPTORS:
            # Conditionally skip the base excludes.
            if any([vd == '~=', vd == '==', vd == '!=', vd == anchor]):
                continue
            else:
                # Set the version value to a string.
                _version_ = str(vds[vd])

                # If the anchor is in the max (greater than) list check if the
                # sentinel version is great than the set version else check if
                # the sentinel version is less than the set version.
                if [i for i in ['>=', '>'] if i == anchor]:
                    if vlv(sentinel) > vlv(_version_):
                        vds[vd] = list()
                else:
                    if vlv(sentinel) < vlv(_version_):
                        vds[vd] = list()

        lesser_boundry = vds['<='] or vds['<']
        greater_boundry = vds['>='] or vds['>']
        if greater_boundry and lesser_boundry:
            # check if the lesser is less than the greater. If so die.
            if vlv(lesser_boundry) < vlv(greater_boundry):
                raise utils.AError(
                    'The package [ %s ] is impossible to be resolved. Its'
                    ' required versions are as follow, "%s"', pkg_name,
                    [i for i in vds.items() if i]
                )
            # If the less than is `=` to the greater than set them as `==`
            elif greater_boundry == lesser_boundry:
                vds['=='] = greater_boundry

        return vds

    def sort_requirements(self, requirements_list=None):
        """Return a sorted ``list`` of requirements.

        :returns: ``list``
        """

        if not requirements_list:
            requirements_list = self.requirements

        # Set the incoming requirements list.
        requirements_list = set(requirements_list)

        # Check if version sanity checking is disabled.
        if self.args['disable_version_sanity']:
            LOG.warn('Version sanity checking has been disabled.')
            # If disabled return a sorted set list of requirements.
            return sorted(requirements_list)

        # Create the base requirement dictionary.
        _requirements = dict()
        for requirement in requirements_list:
            name, versions, markers = self._requirement_name(requirement)
            if name in _requirements:
                req_entry = _requirements[name]
            else:
                req_entry = _requirements[name] = dict()

            # Set the versions
            if 'versions' in req_entry:
                req_versions = req_entry['versions']
            else:
                req_versions = req_entry['versions'] = list()
            req_versions.extend(versions)
            LOG.debug(
                'Found requirements for package "%s": %s', name, req_versions
            )

            # If any markers are defined load sort and set them
            if 'markers' in req_entry:
                req_markers = req_entry['markers']
            else:
                req_markers = req_entry['markers'] = list()

            if markers:
                for marker in markers.split(' or '):
                    req_markers.append(marker.strip().replace(' ', ''))

                LOG.debug(
                    'Found requirement markers for package "%s" with'
                    ' sanitized markers: "%s" original markers: "%s"',
                    name, req_markers, markers
                )

        # Begin sorting the packages.
        packages = list()
        for pkg_name, items in _requirements.items():
            versions = items['versions']
            # Set the list of versions but convert it back to a list for use
            # in a deque.
            versions = list(set(versions))
            vds = dict([(i, list()) for i in VERSION_DESCRIPTORS])
            q = collections.deque(versions)
            while q:
                _version = q.pop()
                for version_descriptor in VERSION_DESCRIPTORS:
                    if version_descriptor in _version:
                        content = _version.split(version_descriptor)[-1]
                        vds[version_descriptor].append(content)
                        break

            LOG.debug(
                'Package: "%s", Raw Version Descriptors: "%s"', pkg_name, vds
            )

            for key, value in vds.items():
                value = list(set(value))
                if value:
                    if key == '!=':
                        vds[key] = sorted(value, reverse=True)
                    else:
                        max_values = any(
                            [key == '>=', key == '>', key == '~=', key == '==']
                        )
                        if max_values:
                            vds[key] = self.version_compare(
                                versions=value,
                                duplicate_handling='max'
                            )
                        else:
                            vds[key] = self.version_compare(
                                versions=value,
                                duplicate_handling='min'
                            )
                else:
                    vds[key] = list()

            LOG.debug(
                'Package: "%s", Compared Version Descriptors: "%s"',
                pkg_name, vds
            )

            vds = self._version_sanity_check(pkg_name=pkg_name, vds=vds)
            LOG.debug(
                'Sanitized versions for package: "%s", Version'
                ' Descriptors: %s', pkg_name, vds
            )
            if '==' in vds and vds['==']:
                packages.append('%s==%s' % (pkg_name, vds['==']))
            elif '~=' in vds and vds['~=']:
                packages.append('%s~=%s' % (pkg_name, vds['~=']))
            else:
                _versions = list()
                for vd in VERSION_DESCRIPTORS:
                    if vds[vd] and isinstance(vds[vd], basestring):
                        _versions.append('%s%s' % (vd, vds[vd]))
                    elif vds[vd] and isinstance(vds[vd], list):
                        _versions.extend(['%s%s' % (vd, i) for i in vds[vd]])
                else:
                    if _versions:
                        build_package = '%s%s' % (
                            pkg_name, ','.join(
                                _versions
                            )
                        )
                    else:
                        build_package = pkg_name

                    if items['markers']:
                        # String transform all markers and set the list
                        set_markers = set(
                            sorted(
                                ['%s' % i for i in set(items['markers'])]
                            )
                        )
                        build_package = '%s;%s' % (
                            build_package,
                            ' or '.join(set_markers)
                        )

                    # Append the built package
                    LOG.info('Built package: "%s"', build_package)
                    packages.append(build_package)

        return sorted(set(packages))

    def _pop_items(self, found_repos, list_items):
        """Remove items within a list.

        :param found_repos: List of found repositories.
        :type found_repos: ``list``
        :param list_items: Name of list within the class to get.
        :type list_items: ``str``
        """
        if self.args['disable_version_sanity']:
            if found_repos:
                LOG.warn(
                    'Version sanity checking is disabled. At present the'
                    ' following potentially duplicate and or conflicting'
                    ' packages were not removed. Items: "%s"', found_repos
                )
        else:
            item_list = getattr(self, list_items)
            for found_repo in found_repos:
                item_list.pop(item_list.index(found_repo))

    def _pop_requirements(self, release):
        """Remove requirement items that are within a requirements list.

        :param release: name of link that is pip installable.
        :type release: ``str``
        """
        name = utils.git_pip_link_parse(repo=release)[0]
        self._pop_items(
            found_repos=[
                i for i in self.requirements
                if self._requirement_name(i)[0] == name
            ],
            list_items='requirements'
        )

    def _pop_branches(self, release):
        """Remove requirement items that are within a branch list.

        :param release: name of link that is pip installable.
        :type release: ``str``
        """
        name = utils.git_pip_link_parse(repo=release)[0]
        self._pop_items(
            found_repos=[
                i for i in self.branches
                if utils.git_pip_link_parse(repo=i)[0] == name
            ],
            list_items='branches'
        )

    def get_requirements(self, report):
        """Load the requirements ``list`` from items within a report.

        :param report: Dictionary report of required items.
        :type report: ``dict``
        """
        for repo in report.values():
            for repo_branch in repo['branches'].values():
                if not isinstance(repo_branch, dict):
                    continue
                elif 'requirements' in repo_branch:
                    for value in repo_branch['requirements'].values():
                        # added support for sanitized requirements. A
                        #  requirement file could have a "-" or an "_" however
                        #  these are equal as far pip is concerned. So all
                        #  requirement items are sanitized to simply be a "-".
                        sanitized_values = list()
                        for item in value:
                            req_item = item.split(';', 1)
                            if len(req_item) > 1:
                                req_item[0] = req_item[0].lower()
                                req_item[0] = req_item[0].replace('_', '-')
                                req = ';'.join(req_item)
                            else:
                                req = req_item[0].lower().replace('_', '-')
                            self.log.debug('Sanitized requirement [ %s ]', req)
                            sanitized_values.append(req)
                        else:
                            self.requirements.extend(sanitized_values)
        else:
            self.requirements = self.sort_requirements()

    def get_branches(self, report):
        """Load the branches ``list`` from items within a report.

        :param report: Dictionary report of required items.
        :type report: ``dict``
        """
        for repo in report.values():
            for repo_branch in repo['branches'].values():
                if not isinstance(repo_branch, dict):
                    continue
                elif repo_branch.get('pip_install_url'):
                    release = repo_branch['pip_install_url']
                    self.branches.append(release)
                    self._pop_requirements(release)
        else:
            self.branches = sorted(list(set(self.branches)))

    def get_releases(self, report):
        """Load the releases ``list`` from items within a report.

        :param report: Dictionary report of required items.
        :type report: ``dict``
        """
        for repo in report.values():
            if 'releases' in repo and isinstance(repo['releases'], list):
                self.releases.extend(repo['releases'])
                for release in repo['releases']:
                    self._pop_requirements(release)
                    self._pop_branches(release)
        else:
            self.releases = sorted(list(set(self.releases)))

    def _store_pool(self):
        """Create wheels within the storage pool directory."""
        built_wheels = utils.get_file_names(
            path=self.args['build_output']
        )

        # Iterate through the built wheels
        for built_wheel in built_wheels:
            _dst_wheel_file_name = os.path.basename(built_wheel)
            # Directory name is being "normalised"
            dst_wheel_file = os.path.join(
                self.args['storage_pool'],
                _dst_wheel_file_name.split('-')[0].lower().replace('_', '-'),
                _dst_wheel_file_name
            )

            # Create destination file
            if os.path.exists(dst_wheel_file):
                dst_size = os.path.getsize(dst_wheel_file)
                src_size = os.path.getsize(built_wheel)
                if dst_size != src_size:
                    LOG.debug(
                        'Wheel found but the sizes are different. The new'
                        ' wheel file will be copied over. Wheel file [ %s ]',
                        dst_wheel_file
                    )
                    self._copy_file(
                        dst_file=dst_wheel_file,
                        src_file=built_wheel
                    )
            else:
                LOG.debug(
                    'Wheel not found copying wheel into place [ %s ]',
                    dst_wheel_file
                )
                # Ensure the directory exists
                self.shell_cmds.mkdir_p(path=os.path.dirname(dst_wheel_file))
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
        """Create symbolic links within a link directory.

        :param full_wheel_path: Full path to wheel on local file system.
        :type full_wheel_path: ``str``
        :param wheel_name: name of wheel.
        :type wheel_name: ``str``
        """
        with utils.ChangeDir(self.args['link_dir']):
            # Create the link using the relative path
            link_path = os.path.join(self.args['link_dir'], wheel_name)
            if os.path.exists(link_path):
                try:
                    # If the link is broken remove it
                    if not os.readlink(link_path):
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

    def _package_clean(self, package, files):
        """Remove links for a given package name if found.

        This method will index the provided link directory and remove any items
        that match the name of the package.

        :param package: Name of a particular package to build.
        :type package: ``str``
        """
        # Set the name of the package from an expected type, git+ or string.
        if 'git+' in package:
            name = utils.git_pip_link_parse(repo=package)[0]
        else:
            name = self._requirement_name(package)[0]

        name = name.replace('-', '_').lower()
        LOG.debug('Checking for package name [ %s ] in link directory.', name)
        for file_name in files:
            base_file_name = os.path.basename(file_name).split('-')[0].lower()
            if name == base_file_name:
                LOG.info('Removed link item from cleanup "%s"', file_name)
                os.remove(file_name)
                files.remove(file_name)

    def build_wheels(self, packages, clean_first=False, force_iterate=False):
        """Create python wheels from a list of packages.

        This method will build all of the wheels from a list of packages. Once
        the loop is completed the wheels items will be moved to the storage
        pool location. Upon the completion of the method the ``build_output``
        directory will be removed.

        :param packages: List of packages to build.
        :type packages: ``list``
        :param clean_first: Enable a search and clean for existing package
        :type clean_first: ``bol``
        :param force_iterate: Force package iteration.
        :type force_iterate: ``bol``
        """
        try:
            if clean_first and self.args['link_dir']:
                files = utils.get_file_names(self.args['link_dir'])
                for package in packages:
                    self._package_clean(package=package, files=files)

            if self.args['pip_bulk_operation'] and not force_iterate:
                req_file = os.path.join(
                    self.args['link_dir'],
                    'build_reqs.txt'
                )
                LOG.info('Requirement file being written: "%s"', req_file)
                self.shell_cmds.mkdir_p(path=os.path.dirname(req_file))
                with open(req_file, 'wb') as f:
                    f.writelines(
                        ['%s\n' % i.encode('UTF-8') for i in packages]
                    )

                self._pip_build_wheels(packages_file=req_file)
            else:
                for package in packages:
                    self._setup_build_wheels(package=package)
            self._store_pool()
        finally:
            utils.remove_dirs(directory=self.args['build_output'])
