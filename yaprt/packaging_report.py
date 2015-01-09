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

import json

from cloudlib import logger

from yaprt import github_repos
from yaprt import utils


LOG = logger.getLogger('repo_builder')


def _create_report(args):
    """Return a package building report.

    :param args: Parsed arguments in dictionary format.
    :type args: ``dict``
    :return: ``dict``
    """
    repo_data = dict()
    ghr = github_repos.GithubRepoPorcess(args=args)
    if args['packages'] or args['packages_file']:
        packages = list()
        if args['packages_file']:
            packages.extend(
                utils.get_items_from_file(file_name=args['packages_file'])
            )

        if args['packages']:
            packages.extend(args['packages'])

        ghr.process_packages(packages=packages)

    for repo in [i for i in args['repo_accounts'] if i]:
        ghr.process_repos(url=repo)

    for repo in [i for i in args['full_repos'] if i]:
        ghr.process_repo_url(url=repo)

    if args['git_install_repos'] or args['git_install_repos_file']:
        git_repos = list()
        if args['git_install_repos_file']:
            git_repos.extend(
                utils.get_items_from_file(
                    file_name=args['git_install_repos_file']
                )
            )

        if args['git_install_repos']:
            git_repos.extend(args['git_install_repos'])

        for repo in [i for i in git_repos if i]:
            name, branch, html_url, url = utils.git_pip_link_parse(repo)
            git_repo = {
                'name': name,
                'git_url': url,
                'html_url': html_url,
                'url': url
            }
            ghr.process_repo(repo=git_repo, branch={'name': branch})

    repo_data.update(ghr.requirements)
    return repo_data


def create_report(args):
    """Create a package building report.

    :param args: Parsed arguments in dictionary format.
    :type args: ``dict``
    """
    repos = _create_report(args=args)
    report_file = utils.get_abs_path(file_name=args['report_file'])
    built_report = json.dumps(repos, indent=4, sort_keys=True)
    LOG.info('Built report: %s', built_report)
    with open(report_file, 'wb') as f:
        f.write(built_report)


def read_report(args):
    """Return a dictionary from a read json file.

    If there is an issue with the loaded JSON file a blank dictionary will be
    returned.

    :param args: Parsed arguments in dictionary format.
    :type args: ``dict``
    :return: ``dict``
    """
    try:
        report_file = utils.get_abs_path(file_name=args['report_file'])
        with open(report_file, 'rb') as f:
            report = json.loads(f.read())
    except IOError:
        return dict()
    else:
        return report