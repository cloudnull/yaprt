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


import requests
import urlparse

from cloudlib import logger

import yaprt as orb
from yaprt import utils

LOG = logger.getLogger('repo_builder')


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

    @utils.retry(Exception)
    def _process_request(self, url):
        """Perform an http request.

        :param url: full url to query
        :type url: ``str``
        :returns: ``dict``
        """
        content = requests.get(url, auth=self.auth)
        if content.status_code >= 300:
            raise SystemExit(content.content)
        else:
            return content.json()

    def _get_repos(self, repo_access):
        """Return a list of repositories from the provided github api.

        :param repo_access: requests head object.
        :type repo_access: ``str``
        :return: ``list``
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

    def _process_repo(self, repo, set_branch=None):
        _repo = self.requirements[repo['name']] = dict()
        _repo['git_url'] = repo['git_url']
        _branches = _repo['branches'] = dict()
        _releases = _repo['releases'] = list()

        url = urlparse.urlparse(repo['html_url'])

        item = dict()
        item['path'] = url.path.strip('/')

        if not repo['url'].endswith('/'):
            repo['url'] = '%s/' % repo['url']

        pip_install = 'git+%s@%s'
        branches_url = urlparse.urljoin(repo['url'], 'branches')
        for key, value in orb.GIT_REQUIREMENTS_MAP.items():
            if key in repo['url']:
                if set_branch:
                    branches = [set_branch]
                else:
                    branches = self._process_request(url=branches_url)
                    tags_url = urlparse.urljoin(repo['url'], 'tags')
                    for tag in self._process_request(url=tags_url):
                        LOG.debug(
                            'Discovered release %s for repo %s',
                            tag['name'],
                            repo['name']
                        )
                        tag_setup = item.copy()
                        tag_setup['file'] = 'setup.py'
                        tag_setup['branch'] = tag['name']
                        if self._check_setup(setup_path=value % tag_setup):
                            _releases.append(
                                pip_install % (_repo['git_url'], tag['name'])
                            )

                for branch in branches:
                    LOG.debug(
                        'Discovered branch "%s" for repo "%s"',
                        branch['name'],
                        repo['name']
                    )
                    item['branch'] = branch['name']
                    branch_data = _branches[branch['name']] = dict()
                    branch_reqs = branch_data['requirements'] = dict()
                    for type_name, file_name in orb.REQUIREMENTS_FILE_TYPES:
                        item['file'] = file_name
                        _requirements = self._check_requirements(value % item)
                        LOG.debug('Found requirements: %s', _requirements)
                        if _requirements:
                            branch_reqs[type_name] = sorted(_requirements)

                    setup_item = item.copy()
                    setup_item['file'] = 'setup.py'
                    if self._check_setup(setup_path=value % setup_item):
                        branch_data['pip_install_url'] = pip_install % (
                            _repo['git_url'], branch['name']
                        )

                break

    def _grab_requirement_files(self, repos):
        """Return a list of dicts used for creating an ansible role manifest.

        :param repos: list of github repositories
        :type repos: ``list``
        :return: ``list``
        """
        for repo in repos:
            self._process_repo(repo=repo)

    @staticmethod
    @utils.retry(Exception)
    def _check_setup(setup_path):
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

    @staticmethod
    @utils.retry(Exception)
    def _check_requirements(requirements_path):
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

    def process_packages(self, packages):
        pkgs = self.requirements['_requirements'] = dict()
        branches = pkgs['branches'] = dict()
        _master = branches['_master'] = dict()
        _requirements = _master['requirements'] = dict()
        _requirements['base_requirements'] = packages

    def process_repo(self, repo, branch=None):
        self._process_repo(
            repo=repo,
            set_branch=branch
        )

    def process_repo_url(self, url):
        self._process_repo(
            repo=self._process_request(url=url)
        )

    def process_repos(self, url):
        """Return json from a request URL.

        This method assumes that you are hitting the github API.

        :param url: Full url to the git api user / org / or repo.
        :type url: ``str``
        :returns: ``dict``
        """
        github_repos = self._get_repos(
            repo_access=requests.head(url, auth=self.auth)
        )
        self._grab_requirement_files(repos=github_repos)
