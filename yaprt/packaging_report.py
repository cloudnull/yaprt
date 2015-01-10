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
import requests
import urlparse

from cloudlib import logger

import yaprt as orb
from yaprt import utils


LOG = logger.getLogger('repo_builder')


def _create_report(args):
    """Return a package building report.

    :param args: Parsed arguments in dictionary format.
    :type args: ``dict``
    :return: ``dict``
    """
    repo_data = dict()
    ghr = GithubRepoPorcess(args=args)
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


class GithubRepoPorcess(object):
    def __init__(self, args):
        """Process github repos for requirements.

        :param args: User defined arguments.
        :type args: ``dict``
        """
        self.requirements = dict()
        self.args = args

        if self.args['git_username']:
            self.auth = (self.args['git_username'], self.args['git_password'])
        else:
            self.auth = None

        self.pip_install = 'git+%s@%s'

    @utils.retry(Exception)
    def _process_request(self, url):
        """Perform an http request.

        If the connection being made to the URL is returned with a 500 error
        this method would raise an exception will will allow the method to
        retry.

        :param url: full url to query
        :type url: ``str``
        :returns: ``dict``
        """
        content = requests.get(url, auth=self.auth)
        if content.status_code >= 300:
            raise utils.AError(content.content)
        else:
            return content.json()

    def _get_repos(self, repo_access):
        """Return a list of repositories from the provided github api.

        :param repo_access: requests head object.
        :type repo_access: ``str``
        :returns: ``list``
        """
        # always pull the headers
        headers = repo_access.__dict__.get('headers')
        link_data = headers.get('link')
        if link_data:
            repo_content = list()
            links = link_data.split(',')
            pages = [i.replace(' ', '') for i in links if 'last' in i]
            page_link = pages[0].split(';')[0]
            page_link = page_link.strip('>').strip('<')
            page_link = page_link.split('=')
            _link, _last_page = page_link
            for page in range(0, int(_last_page)):
                page += 1
                repo_content.extend(
                    self._process_request('%s=%s' % (_link, page))
                )
            else:
                return repo_content
        else:
            return self._process_request(url=repo_access.__dict__['url'])

    def _process_tag_releases(self, name, git_url, repo_data,
                              string_replacement, tags_url):
        """Returns a list of releases from a given repository.

        :param name: Name of a repository.
        :type name: ``str``
        :param git_url: URL for the git repo.
        :type git_url: ``str``
        :param string_replacement: String used to replace items within for
                                   setup files.
        :type string_replacement: ``str``
        :param repo_data: Repository data
        :type repo_data: ``dict``
        :param tags_url: URL for the git repo tag.
        :type tags_url: ``str``
        :returns: ``list``
        """
        releases = list()
        for tag in self._process_request(url=tags_url):
            LOG.debug(
                'Discovered release %s for repo %s',
                tag['name'],
                name
            )
            repo_data['file'] = 'setup.py'
            repo_data['branch'] = tag['name']
            if self._check_setup(setup_path=string_replacement % repo_data):
                releases.append(
                    self.pip_install % (git_url, tag['name'])
                )
        else:
            return releases

    def _process_branch_releases(self, name, git_url, branches, repo_data,
                                 base_branches,  string_replacement):
        """Parse and populate requirements from within branches.

        This method will populate the dictionary items that are within the
        ``base_branches``. While there is nothing being returned within this
        method, the modifications made to the base branches will be available
        to the calling method.

        :param name: Name of a repository.
        :type name: ``str``
        :param git_url: URL for the git repo.
        :type git_url: ``str``
        :param branches: List of all branches in dictionary format
        :type branches: ``list``
        :param repo_data: Repository data
        :type repo_data: ``dict``
        :param base_branches: Dictionary items of branches that will be
                              populated with information parsed within this
                              method.
        :type base_branches: ``dict``
        :param string_replacement: String used to replace items within for
                                   setup files.
        :type string_replacement: ``str``
        """
        for branch in branches:
            LOG.debug(
                'Discovered branch "%s" for repo "%s"',
                branch['name'],
                name
            )
            repo_data['branch'] = branch['name']
            branch_data = base_branches[branch['name']] = dict()
            branch_reqs = branch_data['requirements'] = dict()
            for type_name, file_name in orb.REQUIREMENTS_FILE_TYPES:
                repo_data['file'] = file_name
                _requirements = self._check_requirements(
                    string_replacement % repo_data
                )
                LOG.debug('Found requirements: %s', _requirements)
                if _requirements:
                    branch_reqs[type_name] = sorted(_requirements)

            setup_item = repo_data.copy()
            setup_item['file'] = 'setup.py'
            if self._check_setup(setup_path=string_replacement % setup_item):
                branch_data['pip_install_url'] = self.pip_install % (
                    git_url,
                    branch['name']
                )

    def _process_repo(self, repo, set_branch=None):
        """Parse a given repo and populate the requirements dictionary.

        :param repo: Dictionary object containing git repo data.
        :type repo: ``dict``
        :param set_branch: Set the branch to a given branch
        :type set_branch: ``str`` or ``None``
        """
        _repo = self.requirements[repo['name']] = dict()
        _repo['git_url'] = repo['git_url']
        _branches = _repo['branches'] = dict()
        _releases = _repo['releases'] = list()

        url = urlparse.urlparse(repo['html_url'])

        item = dict()
        item['path'] = url.path.strip('/')

        if not repo['url'].endswith('/'):
            repo['url'] = '%s/' % repo['url']

        branches_url = urlparse.urljoin(repo['url'], 'branches')
        for key, value in orb.GIT_REQUIREMENTS_MAP.items():
            if key in repo['url']:
                if set_branch:
                    branches = [set_branch]
                else:
                    branches = self._process_request(url=branches_url)
                    tags_url = urlparse.urljoin(repo['url'], 'tags')
                    _releases.extend(
                        self._process_tag_releases(
                            name=repo['name'],
                            git_url=_repo['git_url'],
                            repo_data=item.copy(),
                            string_replacement=value,
                            tags_url=tags_url
                        )
                    )

                self._process_branch_releases(
                    name=repo['name'],
                    git_url=_repo['git_url'],
                    repo_data=item,
                    string_replacement=value,
                    branches=branches,
                    base_branches=_branches
                )

                break

    def _grab_requirement_files(self, repos):
        """Return a list of dicts used for creating an ansible role manifest.

        :param repos: list of github repositories
        :type repos: ``list``
        """
        for repo in repos:
            self._process_repo(repo=repo)

    @staticmethod
    @utils.retry(Exception)
    def _check_setup(setup_path):
        """Return ``True`` if a setup file is found within the git url.

        This method is a static method and will retry on any exceptions.

        If the connection being made to the URL is returned with a 500 error
        this method would raise an exception will will allow the method to
        retry.

        :param setup_path: URL to a prospective setup file.
        :type setup_path: ``str``
        :return: ``bol``
        """
        req = requests.head(setup_path)
        LOG.debug(
            'Return code [ %s ] while looking for [ %s ]',
            req.status_code,
            setup_path
        )
        if req.status_code == 200:
            LOG.debug(
                'Found setup.py [ %s ]', setup_path
            )
            return True
        elif req.status_code >= 500:
            raise utils.AError(
                'Connection return information resulted in a failure.'
            )
        else:
            return False

    @staticmethod
    @utils.retry(Exception)
    def _check_requirements(requirements_path):
        """Return a list of items.

        The returned list will contain only items with content. If an item
        begins with a "#" it will be filtered.

        This method is a static method and will retry on any exceptions.

        If the connection being made to the URL is returned with a 500 error
        this method would raise an exception will will allow the method to
        retry.

        :param requirements_path:
        :returns: ``list``
        """
        req = requests.head(requirements_path)
        LOG.debug(
            'Return code [ %s ] while looking for [ %s ]',
            req.status_code,
            requirements_path
        )
        if req.status_code == 200:
            LOG.debug(
                'Found requirements [ %s ]', requirements_path
            )
            req = requests.get(requirements_path)
            return [
                i.split()[0] for i in req.text.splitlines()
                if i
                if not i.startswith('#')
            ]
        elif req.status_code >= 500:
            raise utils.AError(
                'Connection return information resulted in a failure.'
            )
        else:
            return list()

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

    def process_repo(self, repo, branch=None):
        """Process a given repository.

        :param repo: Dictionary object containing git repo data.
        :type repo: ``dict``
        :param branch: Name of a given branch, if undefined this will default
                       to ``None``.
        :type branch: ``dict`` or ``None``
        """
        self._process_repo(
            repo=repo,
            set_branch=branch
        )

    def process_repo_url(self, url):
        """Process a given url for a github

        :param url: Full url to the git api user / org / or repo.
        :type url: ``str``
        """
        self._process_repo(
            repo=self._process_request(url=url)
        )

    def process_repos(self, url):
        """Return json from a request URL.

        This method assumes that you are hitting the github API.

        :param url: Full url to the git api user / org / or repo.
        :type url: ``str``
        """
        github_repos = self._get_repos(
            repo_access=requests.head(url, auth=self.auth)
        )
        self._grab_requirement_files(repos=github_repos)
