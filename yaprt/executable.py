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
import os

from cloudlib import arguments
from cloudlib import indicator
from cloudlib import logger

import yaprt
from yaprt import github_repos
from yaprt import clone_repos
from yaprt import wheel_builder
from yaprt import utils


def _arguments():
    """Return CLI arguments."""
    return arguments.ArgumentParserator(
        arguments_dict=yaprt.ARGUMENTS_DICT,
        epilog='Licensed Apache2',
        title='Python package builder Licensed "Apache 2.0"',
        detail='Openstack package builder',
        description='Rackspace Openstack, Python wheel builder',
        env_name='OS_REPO'
    ).arg_parser()


def _get_report_file(args):
    return os.path.abspath(
        os.path.expanduser(
            args['report_file']
        )
    )


def _create_report(args):
    repo_data = dict()
    ghr = github_repos.GithubRepoPorcess(args=args)

    if args['packages']:
        ghr.process_packages(packages=args['packages'])

    for repo in args['repo_accounts']:
        if repo:
            ghr.process_repos(url=repo)

    for repo in args['full_repos']:
        if repo:
            ghr.process_repo_url(url=repo)

    for repo in args['git_install_repos']:
        if repo:
            name, branch, html_url, url = utils.git_pip_link_parse(repo)

            # TODO(Kevin) this needs to construct the BASIC git-repo dict
            git_repo = {
                'name': name,
                'git_url': url,
                'html_url': html_url,
                'url': url
            }
            git_branch = {
                'name': branch
            }

            ghr.process_repo(repo=git_repo, branch=git_branch)

    repo_data.update(ghr.requirements)
    return repo_data


def create_report(args, log):
    repos = _create_report(args=args)
    report_file = _get_report_file(args=args)
    built_report = json.dumps(repos, indent=4, sort_keys=True)
    log.debug('Built report: %s', built_report)
    with open(report_file, 'wb') as f:
        f.write(built_report)


def _read_report(args):
    report_file = _get_report_file(args=args)
    try:
        with open(report_file, 'rb') as f:
            report = json.loads(f.read())
    except IOError:
        return dict()
    else:
        return report


def store_repos(args, log):
    cgr = clone_repos.CloneGitRepos(user_args=args)
    cgr.store_git_repos(report=_read_report(args=args))


def build_wheels(args, log):
    report = _read_report(args=args)
    wb = wheel_builder.WheelBuilder(user_args=args)
    wb.get_requirements(report=report)
    if args['build_packages']:
        wb.requirements.extend(args['build_packages'])
        wb.requirements = list(set(wb.requirements))

    wb.get_branches(report=report)
    wb.get_releases(report=report)

    if args['build_requirements'] or args['build_packages']:
        log.info('Found requirements: %d', len(wb.requirements))
        wb.build_wheels(packages=wb.requirements)

    if args['build_branches']:
        log.info('Found branch packages: %d', len(wb.branches))
        wb.build_wheels(packages=wb.branches)

    if args['build_releases']:
        log.info('Found releases: %d', len(wb.releases))
        wb.build_wheels(packages=wb.releases, log_build=True)


def main():
    args = _arguments()
    if args['debug'] is True:
        run_spinner = False
        stream_logs = True
    elif args['quiet'] is True:
        run_spinner = False
        stream_logs = False
    else:
        run_spinner = True
        stream_logs = False

    _logging = logger.LogSetup(debug_logging=args['debug'])
    log = _logging.default_logger(
        name='repo_builder',
        enable_stream=stream_logs
    )

    with indicator.Spinner(run=run_spinner):
        if args['parsed_command'] == 'create-report':
            create_report(args=args, log=log)
        elif args['parsed_command'] == 'build-wheels':
            build_wheels(args=args, log=log)
        elif args['parsed_command'] == 'store-repos':
            store_repos(args=args, log=log)

if __name__ == '__main__':
    main()
