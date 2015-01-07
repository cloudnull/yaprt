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

import os

from cloudlib import logger
from cloudlib import shell

from yaprt import packaging_report as pkgr
from yaprt import utils


LOG = logger.getLogger('repo_builder')


def store_repos(args):
    cgr = CloneGitRepos(user_args=args)
    cgr.store_git_repos(report=pkgr.read_report(args=args))


class CloneGitRepos():
    def __init__(self, user_args):
        self.args = user_args
        self.shell_cmds = shell.ShellCommands(
            log_name='repo_builder',
            debug=self.args['debug']
        )

    @staticmethod
    def _clone_command(git_repo, repo_path_name):
        LOG.debug('Cloning into git repo [ %s ]', repo_path_name)
        return ['git', 'clone', git_repo, repo_path_name]

    @staticmethod
    def _update_commands(repo_path_name):
        LOG.debug('Updating git repo [ %s ]', repo_path_name)
        return [
            ['git', 'fetch', '-p', 'origin'],
            ['git', 'pull']
        ]

    def _store_git_repos(self, git_repo):
        """Clone and or update all git repos.

        :param git_repo: ``str`` URL for git repo
        """
        repo_name = os.path.basename(git_repo)
        repo_name = os.path.splitext(repo_name)[0]
        repo_path_name = os.path.join(self.args['git_repo_path'], repo_name)
        if os.path.isdir(repo_path_name):
            repo_git_dir = os.path.join(repo_path_name, '.git')
            if not os.path.isdir(repo_git_dir):
                utils.remove_dirs(directory=repo_path_name)
                self.shell_cmds.run_command(
                    command=' '.join(
                        self._clone_command(git_repo, repo_path_name)
                    )
                )
            else:
                os.chdir(repo_path_name)
                for command in self._update_commands(repo_path_name):
                    self.shell_cmds.run_command(
                        command=' '.join(
                            command
                        )
                    )
        else:
            self.shell_cmds.run_command(
                command=' '.join(
                    self._clone_command(git_repo, repo_path_name)
                )
            )

    def store_git_repos(self, report):
        self.shell_cmds.mkdir_p(path=self.args['git_repo_path'])
        for repo in report.values():
            for key, value in repo.items():
                if key == 'git_url':
                    self._store_git_repos(git_repo=value)
