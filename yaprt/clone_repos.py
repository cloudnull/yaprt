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

"""Module to store git repositories and update them when needed."""

import os

from cloudlib import logger
from cloudlib import shell

from yaprt import packaging_report as pkgr
from yaprt import utils


LOG = logger.getLogger('repo_builder')


def store_repos(args):
    """Store the git repositories locally.

    :param args: Parsed arguments in dictionary format.
    :type args: ``dict``
    """
    cgr = CloneGitRepos(user_args=args)
    cgr.store_git_repos(report=pkgr.read_report(args=args))


class CloneGitRepos(object):
    def __init__(self, user_args):
        """Locally store git repositories.

        :param user_args: Parsed arguments in dictionary format.
        :type user_args: ``dict``
        """
        self.args = user_args
        self.shell_cmds = shell.ShellCommands(
            log_name='repo_builder',
            debug=self.args['debug']
        )

    @staticmethod
    def _clone_command(git_repo, repo_path_name):
        """Return a list of strings that is used to clone a repository.

        :param git_repo: Full git URI.
        :type git_repo: ``str``
        :param repo_path_name: Path to where the git repository will be stored.
        :type repo_path_name: ``str``
        :return: ``list``
        """
        LOG.debug('Cloning into git repo [ %s ]', repo_path_name)
        return ['git', 'clone', git_repo, repo_path_name]

    @staticmethod
    def _update_commands(repo_path_name):
        """Return a list of lists to update a git repository

        :param repo_path_name: Path to where the git repository will be stored.
        :type repo_path_name: ``str``
        :return: ``list``
        """
        LOG.debug('Updating git repo [ %s ]', repo_path_name)
        return [
            ['git', 'fetch', '-p', 'origin'],
            ['git', 'pull']
        ]

    def _run_command(self, command):
        """Run a shell command.

        :param command: list object containing parts of a shell command.
        :type command: ``list``
        """
        data, success = self.shell_cmds.run_command(command=' '.join(command))
        if not success:
            raise OSError(str(data))

    @utils.retry(OSError)
    def _store_git_repos(self, git_repo):
        """Clone and or update all git repositories.

        :param git_repo: URL for git repo
        :type git_repo: ``str``
        """
        # Set the repo name to the base name of the git_repo variable.
        repo_name = os.path.basename(git_repo)
        repo_name = os.path.splitext(repo_name)[0]
        # Set the git repo path.
        repo_path_name = os.path.join(self.args['git_repo_path'], repo_name)

        # If the directory exists update
        if os.path.isdir(repo_path_name):
            # If there is no .git dir remove the target and re-clone
            if not os.path.isdir(os.path.join(repo_path_name, '.git')):
                utils.remove_dirs(directory=repo_path_name)
                self._run_command(
                    command=self._clone_command(git_repo, repo_path_name)
                )
            else:
                # Temporarily change the directory to the repo path.
                with utils.ChangeDir(target_dir=repo_path_name):
                    for command in self._update_commands(repo_path_name):
                        self._run_command(command=command)
        else:
            # Clone the repository
            self._run_command(
                command=self._clone_command(git_repo, repo_path_name)
            )

    def store_git_repos(self, report):
        """Iterate through the git repos update/store them.

        :param report: Dictionary of repositories to iterate through.
        :type report: ``dict``
        """
        # Create the directories path if it doesnt exist.
        self.shell_cmds.mkdir_p(path=self.args['git_repo_path'])

        # Sort and store any git repositories from within a report.
        for repo in report.values():
            for key, value in repo.items():
                if key == 'git_url':
                    self._store_git_repos(git_repo=value)
