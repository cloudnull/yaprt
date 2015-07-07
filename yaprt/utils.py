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

"""Utilities used throughout the project."""


import base64
import functools
import hashlib
import json
import os
import time

from cloudlib import logger
from cloudlib import shell


LOG = logger.getLogger('repo_builder')


def retry(exception, tries=3, delay=1, backoff=1):
    """Retry calling the decorated function using an exponential backoff.

    original from: http://wiki.python.org/moin/PythonDecoratorLibrary#Retry

    :param exception: the exception to check. may be a tuple of
                      exceptions to check
    :type exception: ``Exception`` or ``tuple`
    :param tries: number of times to try (not retry) before giving up
    :type tries: ``int``
    :param delay: initial delay between retries in seconds
    :type delay: ``int``
    :param backoff: backoff multiplier e.g. value of 2 will double the delay
                    each retry
    :type backoff: ``int``
    """
    def deco_retry(f):
        @functools.wraps(f)
        def f_retry(*args, **kwargs):
            mtries, mdelay = tries, delay
            while mtries > 1:
                try:
                    return f(*args, **kwargs)
                except exception as exp:
                    time.sleep(mdelay)
                    mtries -= 1
                    LOG.warn(
                        'Error running process. Remaining attempts [ %s ]'
                        ' Details: [ %s ]', mtries, exp
                    )
                    mdelay *= backoff
            return f(*args, **kwargs)
        return f_retry  # true decorator
    return deco_retry


def git_pip_link_parse(repo):
    """Return a tuple containing the parts of a git repository.

    Example parsing a standard git repo:
      >>> git_pip_link_parse('git+https://github.com/username/repo@tag')
      ('repo',
       'tag',
       None,
       'https://github.com/username/repo',
       'git+https://github.com/username/repo@tag')

    Example parsing a git repo that uses an installable from a subdirectory:
      >>> git_pip_link_parse(
      ...     'git+https://github.com/username/repo@tag#egg=plugin.name'
      ...     '&subdirectory=remote_path/plugin.name'
      ... )
      ('repo',
       'tag',
       'remote_path/plugin.name',
       'https://github.com/username/repo',
       'git+https://github.com/username/repo@tag#egg=plugin.name&'
       'subdirectory=remote_path/plugin.name')

    :param repo: git repo string to parse.
    :type repo: ``str``
    :returns: ``tuple``
    """

    LOG.debug(repo)
    _git_url = repo.split('+')
    if len(_git_url) >= 2:
        _git_url = _git_url[1]
    else:
        _git_url = _git_url[0]

    git_branch_sha = _git_url.split('@')
    if len(git_branch_sha) > 1:
        url, branch = git_branch_sha
    else:
        url = git_branch_sha[0]
        branch = 'master'

    name = os.path.basename(url.split('.git')[0].rstrip('/'))
    _branch = branch.split('#')
    branch = _branch[0]

    plugin_path = None
    # Determine if the package is a plugin type
    if len(_branch) > 1:
        if 'subdirectory' in _branch[-1]:
            plugin_path = _branch[1].split('subdirectory=')[1].split('&')[0]

    return name.lower(), branch, plugin_path, url, repo


def copy_file(src, dst):
    """Copy file from source to destination.

    :param src: Path to source file.
    :type src: ``str``
    :param dst: Path to destination file.
    :type dst: ``str``
    """
    LOG.debug('Copying [ %s ] -> [ %s ]', src, dst)
    with open(src, 'rb') as open_src:
        with open(dst, 'wb') as open_dst:
            while True:
                buf = open_src.read(24 * 1024)
                if not buf:
                    break
                else:
                    open_dst.write(buf)


def get_abs_path(file_name):
    """Return the absolute path from a given path.

    :param file_name: $PATH
    :type file_name: ``str``
    :returns: ``str``
    """
    return os.path.abspath(os.path.expanduser(file_name))


def stip_quotes(item):
    """Return an item with any quotes stripped from the beginning and end.

    :param item: String to use.
    :type item: ``str``
    :returns: ``str``
    """
    if item:
        return item.strip("""\'\"""")
    else:
        return item


def get_items_from_file(file_name):
    """Return a list of items from a local file.

    Items in a file can be separated with either a space or by lines. If an
    item within the parsed list has a quote or double quote in the beginning or
    the end of the item it will be stripped.

    :param file_name: $PATH to the file name that will be opened and parsed.
    :type file_name: ``str``
    :returns: ``list``
    """
    items = list()
    with open(get_abs_path(file_name=file_name), 'rb') as f:
        for item in [i.strip() for i in f.readlines()]:
            # Split on whitespace and strip both ' and " from the sting.
            items.extend([stip_quotes(item=i) for i in item.split()])
        else:
            return items


def get_file_names(path):
    """Return a list of all files in the vars/repo_packages directory.

    :param path: $PATH to search for files
    :type path: ``str``
    :returns: ``list``
    """
    files = list()
    for fpath, _, afiles in os.walk(get_abs_path(file_name=path)):
        for afile in afiles:
            files.append(os.path.join(fpath, afile))
    else:
        LOG.debug('Found %d files', len(files))
        return files


def remove_dirs(directory):
    """Delete a directory recursively.

    :param directory: $PATH to directory.
    :type directory: ``str``
    """
    directory = get_abs_path(file_name=directory)
    LOG.info('Removing directory [ %s ]', directory)
    for file_name in get_file_names(path=directory):
        try:
            os.remove(file_name)
        except OSError as exp:
            LOG.error(str(exp))

    dir_names = list()
    for dir_name, _, _ in os.walk(directory):
        dir_names.append(dir_name)

    dir_names = sorted(dir_names, reverse=True)
    for dir_name in dir_names:
        try:
            os.removedirs(dir_name)
        except OSError as exp:
            if exp.errno != 2:
                LOG.error(str(exp))
            pass


def hash_return(local_file, hash_type='sha256'):
    """Return the hash of a local file object.

    This function will support any hash type available within ``hashlib``.

    Example:
        >>> hash_return(local_file='/path/file_name')
        e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855

    :param local_file: $PATH Local file
    :type local_file: ``str``
    :param hash_type: Type of hash to use. IE: md5, sha256
    :type hash_type: ``str``
    :returns: ``str``
    """
    def calc_hash():
        """Read the hash.

        :returns: ``bytes``
        """
        return file_object.read(128 * hash_function.block_size)

    local_file = get_abs_path(file_name=local_file)
    if os.path.isfile(local_file):
        hash_function = getattr(hashlib, hash_type)
        hash_function = hash_function()
        with open(local_file, 'rb') as file_object:
            for chk in iter(calc_hash, ''):
                if isinstance(chk, bytes):
                    hash_function.update(chk)
                else:
                    hash_function.update(chk.encode('utf-8'))

        return hash_function.hexdigest()


def read_report(args):
    """Return a dictionary from a read json file.
    If there is an issue with the loaded JSON file a blank dictionary will be
    returned.
    :param args: Parsed arguments in dictionary format.
    :type args: ``dict``
    :return: ``dict``
    """
    try:
        report_file = get_abs_path(file_name=args['report_file'])
        with open(report_file, 'rb') as f:
            report = json.loads(f.read())
    except IOError:
        return dict()
    else:
        return report


class ChangeDir(object):
    """Change directory class.

    The ChangeDir class is used to temporarily change the working directory to
    a given path. This class can be used as a context manager as well as a
    standard object that might fit in well could be used within a try / finally
    block.

    Example context manager:
      >>> with ChangeDir('/tmp/path'):
      ...    print('things to do')

    Example as object:
      >>> try:
      ...     change_dir = ChangeDir('/tmp/path')
      ...     change_dir.enter()
      ...     print('things to do')
      ... finally:
      ...     change_dir.exit()
    """
    def __init__(self, target_dir):
        """Temporarily change to a target directory."""
        self._target_dir = target_dir
        self._cwd = os.getcwd()

    def __enter__(self):
        try:
            os.chdir(self._target_dir)
        except OSError as exp:
            raise AError(
                'There was an error changing the directory. Error: "%s"',
                str(exp)
            )

    def __exit__(self, *args):
        os.chdir(self._cwd)

    def exit(self):
        self.__exit__()

    def enter(self):
        self.__enter__()


class _BaseException(Exception):
    """Base exception class.

    This exception class can take arguments and string replacement items in
    either dict or tuple format. This exception class will also write the
    formatted message to a logged error message.

    Note:
      When using dictionary format the first item in passed to the exception
    should be a sting and the second should be a dictionary. All other items
    will be ignored.

    Example tuple format:
      >>> raise AError('message: %s %s', 'others', 'things')
      AError: message: other things

    Example dict format:
      >>> raise AError('message: %(a)s %(b)s', {'a': 'others', 'b': 'things'}
      ... )
      AError: message: others things
    """
    def __init__(self, *args):
        """Base exception.

        :param args: list of arguments to pass to an exception
        :type args: ``list`` or ``tuple``
        """
        if len(args) > 1:
            format_message = args[0]
            try:
                if isinstance(args[1], dict):
                    replace_items = args[1]
                else:
                    replace_items = tuple([str(i) for i in args[1:]])

                message = format_message % replace_items
            except TypeError as exp:
                message = (
                    'The exception message was not formatting correctly.'
                    ' Error: [ %s ]. This was the original'
                    ' message: "%s".' % (exp, args)
                )
        else:
            message = args[0]

        super(_BaseException, self).__init__(message)
        LOG.error(self.message)


class AError(_BaseException):
    """An error has occurred."""

    pass


class RepoBaseClass(object):
    def __init__(self, user_args, log_object):
        self.args = user_args
        self.shell_cmds = shell.ShellCommands(
            log_name='repo_builder',
            debug=self.args['debug']
        )
        self.log = log_object

    def _run_command(self, command, skip_failure=False):
        """Run a shell command.

        :param command: list object containing parts of a shell command.
        :type command: ``list``
        """
        data, success = self.shell_cmds.run_command(command=' '.join(command))
        self.log.debug(
            'Command Data: [ %s ], Success: [ %s ]', data, success
        )
        if not success and not skip_failure:
            self.log.error(str(data))
            raise SystemExit(str(data))
        elif not success and skip_failure:
            self.log.warn(
                'Command failed but the failure was skipped. Command Data:'
                ' [ %s ], Success: [ %s ]', data, success
            )

    @staticmethod
    def split_git_branches(git_branch):
        """Split the branches to see if there are multiple items.

        :param git_branch: branch connection string.
        :type git_branch: ``str``
        """
        git_branches = git_branch.split(',')
        int_branch = base64.b64encode('-'.join(git_branches))
        return [i.strip() for i in git_branches], int_branch[:32]
