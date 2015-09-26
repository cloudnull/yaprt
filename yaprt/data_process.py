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

import os

from cloudlib import logger

from yaprt import utils


LOG = logger.getLogger('data_processing')


def package_processing(args, repo_data):
    user_packages = repo_data['__user__'] = dict()
    requirements = user_packages['requirements'] = list()
    if args['packages'] or args['packages_file']:
        if args['packages_file']:
            requirements.extend(
                utils.get_items_from_file(file_name=args['packages_file'])
            )

        if args['packages']:
            requirements.extend(args['packages'])

        user_packages['requirements'] = list(set(requirements))

    git_repos = list()
    if args['git_install_repos'] or args['git_install_repos_file']:
        if args['git_install_repos_file']:
            LOG.debug('install repos file: %s', args['git_install_repos_file'])
            git_repos.extend(
                utils.get_items_from_file(
                    file_name=args['git_install_repos_file']
                )
            )

        if args['git_install_repos']:
            LOG.debug('install repos: %s', args['git_install_repos'])
            git_repos.extend(args['git_install_repos'])

    return git_repos


def processing_report(args):
    git_repos = list()
    for item in utils.read_report(args=args).values():
        branches = item.get('branches')
        for key, value in branches.items():
            if 'original_data' == key:
                git_repos.append(value)

    return git_repos


def organize_data(args):
    """Return a package building report.

    :param args: Parsed arguments in dictionary format.
    :type args: ``dict``
    :return: ``dict``
    """
    repo_data = dict()

    if args['parsed_command'] == 'create-report':
        git_repos = package_processing(args, repo_data)
    else:
        git_repos = processing_report(args)

    LOG.debug('Git repos: %s', git_repos)
    for repo in [i for i in git_repos if i]:
        name, branch, plugin_path, url, o_data = utils.git_pip_link_parse(repo)
        if plugin_path:
            name = '%s_plugin_pkg_%s' % (name, os.path.basename(plugin_path))
        _repo_data = repo_data[name] = dict()
        _repo_data['name'] = name
        _repo_data['branch'] = branch
        _repo_data['plugin_path'] = plugin_path
        _repo_data['git_url'] = url
        _repo_data['original_data'] = o_data

    return repo_data
