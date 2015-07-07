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

import yaprt
from yaprt import utils


LOG = logger.getLogger('repo_builder')


def store_repos(args, repo_list):
    """Store the git repositories locally.

    :param args: Parsed arguments in dictionary format.
    :type args: ``dict``
    :param repo_list: List of git repos to iterate through
    :type repo_list: ``list``
    """
    # Create a basic git config file if one is not already found.
    git_config_file = os.path.join(os.path.expanduser('~'), '.gitconfig')
    if not os.path.isfile(git_config_file):
        with open(git_config_file, 'w') as f:
            f.write(yaprt.GITCONFIGBSAIC)

    cgr = CloneGitRepos(user_args=args)
    # The repo list is sanitized before using it
    cgr.store_git_repos(repo_list=repo_list)


class CloneGitRepos(utils.RepoBaseClass):
    def __init__(self, user_args):
        """Locally store git repositories.

        :param user_args: Parsed arguments in dictionary format.
        :type user_args: ``dict``
        """
        super(CloneGitRepos, self).__init__(
            user_args=user_args,
            log_object=LOG
        )

    @utils.retry(SystemExit)
    def _run_clone(self, git_repo, repo_path_name):
        """Return a list of strings that is used to clone a repository.

        :param git_repo: Full git URI.
        :type git_repo: ``str``
        :param repo_path_name: Path to where the git repository will be stored.
        :type repo_path_name: ``str``
        """
        LOG.debug('Cloning into git repo [ %s ]', repo_path_name)
        self._run_command(command=['git', 'clone', git_repo, repo_path_name])
        self._run_add_yaprt_branch(repo_path_name=repo_path_name)

    def _run_add_yaprt_branch(self, repo_path_name):
        with utils.ChangeDir(target_dir=repo_path_name):
            self._run_command(
                command=['git', 'checkout', '-B', 'yaprt-integration'],
                skip_failure=True
            )

    def _run_update(self, git_repo, git_branch):
        """Run updates from within a given cloned repository.

        :param git_repo: URL for git repo
        :type git_repo: ``str``
        :param git_branch: Branch for git repo
        :type git_branch: ``str``
        """

        self.log.info('Processing repo: [ %s ]', git_repo)
        git_branches, int_branch = self.split_git_branches(
            git_branch=git_branch
        )

        # Fetch all existing remotes first.
        self._run_command(command=['git', 'fetch', '--all'])

        # Ensure that our working directory is clean
        self._run_command(
            command=['git', 'clean', '-f', '-d'],
            skip_failure=True
        )

        # Ensure we have our yaprt staging point within the repo
        self._run_command(
            command=['git', 'checkout', '-B', 'yaprt-integration'],
            skip_failure=True
        )

        # Verify if the integration branch exists, If so, Nuke it, else pass.
        self._run_command(
            command=['git', 'branch', '-D', "'%s'" % int_branch],
            skip_failure=True
        )

        revert_cherrypick_on_fail = False
        if len(git_branches) > 1:
            LOG.info(
                'Creating repo integration branch with the following %s',
                git_branches
            )
            commands = [
                ['git', 'fetch', git_repo, git_branches[0]],
                ['git', 'checkout', 'FETCH_HEAD'],
                ['git', 'checkout', '-b', "'%s'" % int_branch]
            ]
            # Cherry-pick against the newly built branches
            revert_cherrypick_on_fail = True
            for to_pick in git_branches[1:]:
                commands.extend(
                    [
                        ['git', 'fetch', git_repo, to_pick],
                        ['git', 'cherry-pick', '-x', 'FETCH_HEAD']
                    ]
                )
        else:
            LOG.info('Updating git repo [ %s ]', git_repo)
            commands = [
                ['git', 'fetch', git_repo, git_branch],

            ]
            if 'refs/changes' in git_branch:
                commands.extend(
                    [
                        ['git', 'checkout', 'FETCH_HEAD'],
                        ['git', 'checkout', '-b', "'%s'" % int_branch]
                    ]
                )
            else:
                commands.extend(
                    [
                        ['git', 'checkout', git_branch],
                        ['git', 'pull', 'origin', git_branch]
                    ]
                )

        try:
            for command in commands:
                self._run_command(command=command)
        except SystemExit:
            if revert_cherrypick_on_fail:
                # Abort the cherry-pick to ensure the history is clean
                self._run_command(
                    command=['git', 'cherry-pick', '--abort'],
                    skip_failure=True
                )
                raise utils.AError(
                    'Applying patches to %s using the following %s has failed',
                    git_repo, git_branch
                )
            else:
                raise utils.AError(
                    'Failed to complete update process for %s using %s',
                    git_repo, git_branch
                )

    @utils.retry(Exception)
    def _store_git_repos(self, git_repo, git_branch):
        """Clone and or update all git repositories.

        :param git_repo: URL for git repo
        :type git_repo: ``str``
        :param git_branch: Branch for git repo
        :type git_branch: ``str``
        """
        # Set the repo name to the base name of the git_repo variable.
        repo_name = os.path.basename(git_repo)

        # Set the git repo path.
        repo_path_name = os.path.join(self.args['git_repo_path'], repo_name)

        # If there is no .git dir remove the target and re-clone
        if not os.path.isdir(os.path.join(repo_path_name, '.git')):
            # If the directory exists update
            if os.path.isdir(repo_path_name):
                utils.remove_dirs(directory=repo_path_name)

            # Clone the main repos
            self._run_clone(git_repo, repo_path_name)

        # Temporarily change the directory to the repo path.
        with utils.ChangeDir(target_dir=repo_path_name):
            self._run_update(git_repo=git_repo, git_branch=git_branch)

    def store_git_repos(self, repo_list):
        """Iterate through the git repos update/store them.

        :param repo_list: List of git repos to iterate through
        :type repo_list: ``list`` || ``set``
        """
        # Create the directories path if it doesnt exist.
        self.shell_cmds.mkdir_p(path=self.args['git_repo_path'])

        # Sort and store any git repositories from within the list.
        for repo, branch in repo_list:
            LOG.debug('Repo to clone: [ %s ]', repo)
            self._store_git_repos(git_repo=repo, git_branch=branch)
