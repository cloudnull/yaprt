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

import json
import os
import urlparse

from cloudlib import logger

import yaprt
from yaprt import utils


LOG = logger.getLogger('repo_builder')


def _create_report(args, organize_data):
    """Return a package building report.

    :param args: Parsed arguments in dictionary format.
    :type args: ``dict``
    :param organize_data: Built data from all processed repos and packages
    :type organize_data: ``dict``
    :return: ``dict``
    """
    repo_data = dict()
    grp = GitRepoProcess(user_args=args)
    if '__user__' in organize_data and organize_data['__user__']:
        # Remove any user defined packages from the organized data
        packages = organize_data.pop('__user__')
        requirements = packages['requirements']
        grp.process_packages(packages=requirements)

    for git_repo in organize_data.values():
        LOG.info('Git repo: %s', git_repo)
        grp.process_repo(repo=git_repo)

    repo_data.update(grp.requirements)
    return repo_data


def create_report(args, organize_data):
    """Create a package building report.

    :param args: Parsed arguments in dictionary format.
    :type args: ``dict``
    """
    repos = _create_report(args=args, organize_data=organize_data)
    report_file = utils.get_abs_path(file_name=args['report_file'])
    built_report = json.dumps(repos, indent=4, sort_keys=True)
    LOG.info('Built report: %s', built_report)
    with open(report_file, 'w') as f:
        f.write(built_report)


class GitRepoProcess(utils.RepoBaseClass):
    def __init__(self, user_args):
        """Process github repos for requirements.

        :param user_args: User defined arguments.
        :type user_args: ``dict``
        """
        super(GitRepoProcess, self).__init__(
            user_args=user_args,
            log_object=LOG
        )

        self.requirements = dict()
        self.pip_install = 'git+%s@%s'

    def _process_sub_plugin(self, requirement, repo_data):
        """process the entry like a subdirectory package.

        :param requirement: Name of the requirement
        :type requirement: ``str``
        :param repo_data: Repository data
        :type repo_data: ``dict``
        """
        requirement_item = requirement.split('-e', 1)[-1].strip()
        try:
            requirement_url = urlparse.urlparse(requirement_item)
            assert all([requirement_url.scheme, requirement_url.netloc])
            assert requirement_url.scheme in ['https', 'http', 'git']
        except AssertionError:
            item_name = os.path.basename(requirement_item)
            item_req = self.pip_install % (
                repo_data['git_url'],
                repo_data['branch']
            )
            repo = '%s#egg=%s&subdirectory=%s' % (
                item_req, item_name, requirement_item
            )
        else:
            repo = requirement_url

        self.process_repo(repo=self.define_new_repo(repo=repo))

    def define_new_repo(self, repo):
        """From a repo entry return a dict object with its data.

        :param repo: repository string
        :type repo: ``str``
        :returns: ``dict``
        """
        name, branch, plugin_path, url, o_data = utils.git_pip_link_parse(repo)
        if plugin_path:
            name = '%s_plugin_pkg_%s' % (name, os.path.basename(plugin_path))
        # Process the new requirement item
        return {
            'name': name,
            'branch': branch,
            'plugin_path': plugin_path,
            'git_url': url,
            'original_data': o_data
        }

    def _process_repo_requirements(self, repo_data, base_report_data):
        """Parse and populate requirements from within branches.

        This method will populate the dictionary items that are within the
        ``base_branches``. While there is nothing being returned within this
        method, the modifications made to the base branches will be available
        to the calling method.

        :param repo_data: Repository data
        :type repo_data: ``dict``
        :param base_report_data: Dictionary items of branches that will be
                                 populated with information parsed within this
                                 method.
        :type base_report_data: ``dict``
        """
        name = utils.git_pip_link_parse(repo=repo_data['original_data'])[0]
        repo_path = os.path.join(self.args['git_repo_path'], name)
        if repo_data['plugin_path']:
            repo_path = os.path.join(repo_path, repo_data['plugin_path'])

        with utils.ChangeDir(repo_path):
            LOG.debug(
                'Discovered branch "%s" for repo "%s"',
                repo_data['branch'],
                repo_data['name']
            )

            git_branches, int_branch = self.split_git_branches(
                git_branch=repo_data['branch']
            )
            patched_from = None
            if len(git_branches) > 1 or 'refs/changes' in repo_data['branch']:
                repo_data['branch'] = int_branch
                patched_from = True

            self._run_command(command=['git', 'checkout', repo_data['branch']])
            branch_data = base_report_data[repo_data['branch']] = dict()
            # Record the items that make up a patched branch
            if patched_from:
                branch_data['patched_from'] = git_branches
            branch_reqs = branch_data['requirements'] = dict()

            if 'yaprtignorerequirements=true' in repo_data['original_data']:
                requirement_files = list()
            else:
                requirement_files = yaprt.REQUIREMENTS_FILE_TYPES

            for type_name, file_name in requirement_files:
                file_path = os.path.join(repo_path, file_name)
                if os.path.isfile(file_path):
                    repo_data['file'] = file_name
                    with open(file_path, 'r') as f:
                        _file_requirements = f.readlines()

                    # If the requirement file has a -e item within it treat
                    #  it like a local subdirectory plugin and process it.
                    _requirements = list()
                    for item in _file_requirements:
                        requirement = item.split('#')[0].strip()
                        if requirement.startswith('-e'):
                            if requirement.endswith('.'):  # skip if "-e ."
                                continue
                            elif 'git+' in item:
                                repo_str = item.split('-e')[-1].strip()
                                self.process_repo(
                                    repo=self.define_new_repo(
                                        repo=repo_str
                                    )
                                )
                            else:
                                self._process_sub_plugin(
                                    requirement=requirement,
                                    repo_data=repo_data
                                )
                        else:
                            _requirements.append(requirement)

                    _requirements = [
                        i.split('#')[0].strip() for i in _requirements
                        if not i.startswith('#')
                        if i.strip()
                    ]

                    LOG.debug('Found requirements: %s', _requirements)
                    if _requirements:
                        branch_reqs[type_name] = sorted(_requirements)

            setup_file_path = os.path.join(repo_path, 'setup.py')
            if os.path.isfile(setup_file_path):
                branch_data['pip_install_url'] = repo_data['original_data']

    def _process_repo(self, repo):
        """Parse a given repo and populate the requirements dictionary.

        :param repo: Dictionary object containing git repo data.
        :type repo: ``dict``
        """
        _repo = self.requirements[repo['name']] = dict()
        _repo['git_url'] = repo['git_url']
        report_data = _repo['branches'] = dict()

        report_data['original_data'] = repo['original_data']
        if not repo['git_url'].endswith('/'):
            repo['git_url'] = '%s/' % repo['git_url']

        LOG.info('Processing repo for [ %s ]', repo['name'])
        self._process_repo_requirements(
            repo_data=repo.copy(),
            base_report_data=report_data
        )

    def process_packages(self, packages):
        """If packages were defined  by the user add them to the requirements.

        These "packages" will be added within the the requirements as a
        special item which should eliminate collisions.

        :param packages: list of packages that were user defined.
        :type packages: ``list``
        :return:
        """
        pkgs = self.requirements['_requirements_'] = dict()
        branches = pkgs['branches'] = dict()
        _master = branches['_master_'] = dict()
        _requirements = _master['requirements'] = dict()
        _requirements['base_requirements'] = packages

    def process_repo(self, repo):
        """Process a given repository.

        :param repo: Dictionary object containing git repo data.
        :type repo: ``dict``
        """
        self._process_repo(repo=repo)
