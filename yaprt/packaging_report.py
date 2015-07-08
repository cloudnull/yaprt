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

    @staticmethod
    def define_new_repo(repo):
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

    def _branch_data(self, repo_data, base_report_data, repo_path):
        """Return branch data.

        :param repo_data: Repository data
        :type repo_data: ``dict``
        :param base_report_data: Base entry for the report
        :type base_report_data: ``dict``
        :param repo_path: Path to repo
        :type repo_path: ``str``
        :returns:``tuple``
        """
        LOG.info(
            'Discovered branch "%s" for repo "%s"',
            repo_data['branch'],
            repo_data['name']
        )
        git_branches, int_branch = self.split_git_branches(
            git_branch=repo_data['branch']
        )
        patched = False
        if len(git_branches) > 1 or 'refs/changes' in repo_data['branch']:
            repo_data['branch'] = int_branch
            patched = True

        self._run_command(command=['git', 'checkout', repo_data['branch']])
        branch_data = base_report_data[repo_data['branch']] = dict()
        branch_reqs = branch_data['requirements'] = dict()
        # Record the items that make up a patched branch
        if patched:
            branch_data['patched_from'] = git_branches

        setup_file_path = os.path.join(repo_path, 'setup.py')
        egg_data_created = False
        if os.path.isfile(setup_file_path):
            # generate egg info, skip it if this raises an error
            egg_data_created = self._run_command(
                skip_failure=True,
                command=['python', 'setup.py', 'egg_info']
            )
            branch_data['pip_install_url'] = repo_data['original_data']

        return branch_reqs, egg_data_created

    def _process_dependency_links(self, dependency_link_files):
        """Process all dependency links found.

        :param dependency_link_files: Files that contain requirements that are
                                      external
        :type dependency_link_files: ``list``
        """
        for dependency_file in dependency_link_files:
            with open(dependency_file, 'r') as f:
                dependencies = [
                    i.strip() for i in f.readlines() if i.strip()
                ]

            for dependency in dependencies:
                self.process_repo(
                    repo=self.define_new_repo(
                        repo=dependency
                    )
                )

    def _get_requirement_files(self, repo_data, repo_path, egg_data_created):
        """Return all requirement files.

        :param repo_data: Repository data
        :type repo_data: ``dict``
        :param egg_data_created: Test if egg data was created
        :type egg_data_created: ``bol``
        :param repo_path: Path to repo
        :type repo_path: ``str``
        :returns:``list``
        """
        if 'yaprtignorerequirements=true' in repo_data['original_data']:
            return list()

        requirement_files = list()
        if egg_data_created:
            dependency_link_files = list()
            for i, _, _ in os.walk(repo_path):
                if 'egg-info' in i:
                    req_file = os.path.join(i, 'requires.txt')
                    if os.path.isfile(req_file):
                        LOG.info('Loaded requirement file: %s', req_file)
                        requirement_files.append(req_file)
                    dep_file = os.path.join(i, 'dependency_links.txt')
                    if os.path.isfile(dep_file):
                        LOG.info('Loaded dependency file: %s', dep_file)
                        dependency_link_files.append(dep_file)
            else:
                self._process_dependency_links(
                    dependency_link_files=dependency_link_files
                )

        # Add all local requirement txt files if they're found
        for i in yaprt.REQUIREMENTS_FILE_TYPES:
            requirement_file = os.path.join(repo_path, i)
            if os.path.isfile(requirement_file):
                requirement_files.append(requirement_file)
        else:
            return requirement_files

    def _get_sanitized_requirements(self, requirement_files):
        """Return sanitized requirements.

        :param requirement_files: list of requirement files.
        :type requirement_files: ``list``
        :returns: ``list``
        """
        LOG.info('Loaded requirement files: %s', requirement_files)
        base_sections = dict()
        for requirement_file in requirement_files:
            with open(requirement_file, 'r') as f:
                new_sections = self._get_requirement_sections(
                    sanitized_requirements=[
                        i.split('#')[0].strip() for i in f.readlines()
                        if not i.startswith('#')
                        if i.strip()
                    ]
                )
                utils.merge_dict(
                    base_items=base_sections,
                    new_items=new_sections
                )
        else:
            return base_sections


    @staticmethod
    def _get_requirement_sections(sanitized_requirements):
        """Return requirement sections.

        :param sanitized_requirements: list of requirements that have been
                                       sanitized.
        :type sanitized_requirements: ``list``
        :returns: ``dict``
        """
        sections = dict()
        new_sec = sections['default'] = list()
        for req in sanitized_requirements:
            dirived_section_check = req.split(';')
            if len(dirived_section_check) > 1:
                dirived_section_name = ':%s' % dirived_section_check[-1]
                # A marker could have an "or" in it, which means that the
                #  package is installable in multiple contexts as such this
                #  will load the requirement into multiple sections if found.
                for marker in dirived_section_name.split(' or '):
                    marker = marker.strip().replace(' ', '')
                    dirived_section = utils.return_list(
                        dict_obj=sections,
                        key=marker
                    )
                    dirived_section.append(dirived_section_check[0])
            elif req.startswith('['):
                section_name = req.lstrip('[').rstrip(']')
                new_sec = utils.return_list(
                    dict_obj=sections,
                    key=section_name
                )
            else:
                new_sec.append(req)

        for section, items in sections.items():
            sections[section] = list(set(sorted(items)))
        else:
            LOG.info('Requirement Sections: %s', sections)
            return sections

    def _process_requirements(self, sections, repo_data, branch_reqs):
        """Process all requirements.

        :param sections: requirement dict with list of requirements.
        :type sections: ``dict``
        :param repo_data All repo data in dict format.
        :type repo_data: ``dict``
        :param branch_reqs: specific requirements based on sections.
        :type branch_reqs: ``dict``
        """
        for section, requirements in sections.items():
            requirements = set(requirements)
            LOG.debug('Sorted requirements: %s', requirements)
            normal_requirements = list()
            for requirement in requirements:
                # If the requirement file has a -e item within it treat
                #  it like a local subdirectory plugin and process it.
                LOG.debug('Requirement item: "%s"', requirement)
                if not requirement.startswith('-e'):
                    normal_requirements.append(requirement)
                else:
                    repo_str = requirement.split('-e')[-1]
                    repo_str = repo_str.split('#')[0].strip()
                    if repo_str.endswith('.'):  # skip if "-e ."
                        LOG.info('Skipping "-e ." value: %s', repo_str)
                    elif 'git+' in repo_str:
                        LOG.info('Git dependency link: %s', repo_str)
                        self.process_repo(
                            repo=self.define_new_repo(
                                repo=repo_str
                            )
                        )
                    else:
                        LOG.info('Subdirectory plugin: %s', repo_str)
                        self._process_sub_plugin(
                            requirement=repo_str,
                            repo_data=repo_data
                        )
            else:
                LOG.debug('Found requirements: %s', normal_requirements)
                branch_reqs[section] = normal_requirements

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

        LOG.info('Repo path "%s"', repo_path)
        with utils.ChangeDir(repo_path):
            branch_reqs, egg_data_created = self._branch_data(
                repo_data=repo_data,
                base_report_data=base_report_data,
                repo_path=repo_path
            )

            requirement_files = self._get_requirement_files(
                repo_data=repo_data,
                repo_path=repo_path,
                egg_data_created=egg_data_created
            )

            sections = self._get_sanitized_requirements(
                requirement_files=requirement_files
            )

            self._process_requirements(
                sections=sections,
                repo_data=repo_data,
                branch_reqs=branch_reqs
            )

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
        _requirements['default'] = list(sorted(set(packages)))

    def process_repo(self, repo):
        """Process a given repository.

        :param repo: Dictionary object containing git repo data.
        :type repo: ``dict``
        """
        self._process_repo(repo=repo)
