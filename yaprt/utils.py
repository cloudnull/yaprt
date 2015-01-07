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


import functools
import hashlib
import os
import time

from cloudlib import logger

LOG = logger.getLogger('repo_builder')


def retry(ExceptionToCheck, tries=3, delay=1, backoff=1):
    """Retry calling the decorated function using an exponential backoff.

    original from: http://wiki.python.org/moin/PythonDecoratorLibrary#Retry

    :param ExceptionToCheck: the exception to check. may be a tuple of
                             exceptions to check
    :type ExceptionToCheck: Exception or tuple
    :param tries: number of times to try (not retry) before giving up
    :type tries: int
    :param delay: initial delay between retries in seconds
    :type delay: int
    :param backoff: backoff multiplier e.g. value of 2 will double the delay
                    each retry
    :type backoff: int
    """
    def deco_retry(f):
        @functools.wraps(f)
        def f_retry(*args, **kwargs):
            mtries, mdelay = tries, delay
            while mtries > 1:
                try:
                    return f(*args, **kwargs)
                except ExceptionToCheck:
                    time.sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
            return f(*args, **kwargs)
        return f_retry  # true decorator
    return deco_retry


def git_pip_link_parse(repo):
    _git_url = repo.split('+')[1]
    url, branch = _git_url.split('@')
    html_url = os.path.splitext(url)[0].rstrip('/')
    name = os.path.basename(os.path.splitext(url)[0].rstrip('/'))
    _branch = branch.split('#')
    branch = _branch[0]
    if len(_branch) > 1:
        sub_path = _branch[1].split('subdirectory=')[1].split('&')[0]
        html_url = '%s/%s' % (html_url, sub_path)
    return name.lower(), branch, html_url, url


def copy_file(src, dst):
    """Copy file from source to destination.

    :param src: ``str`` Path to source file.
    :param dst: ``str`` Path to destination file.
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
    return os.path.abspath(os.path.expanduser(file_name))


def get_items_from_file(file_name):
    items = list()
    with open(get_abs_path(file_name=file_name), 'rb') as f:
        for item in [i.strip() for i in f.readlines()]:
            # Split on whitespace and strip both ' and " from the sting.
            items.extend([i.strip("""\'\"""") for i in item.split()])
        else:
            return items


def get_file_names(path):
    """Return a list of all files in the vars/repo_packages directory.

    :param path: ``str``  $PATH to search for files
    """
    files = list()
    for fpath, _, afiles in os.walk(path):
        for afile in afiles:
            files.append(os.path.join(fpath, afile))
    else:
        LOG.debug('Found %d files', len(files))
        return files


def remove_dirs(directory):
    """Delete a directory recursively.

    :param directory: ``str`` $PATH to directory.
    """
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


class ChangeDir(object):
    def __init__(self, target_dir):
        self.target_dir = target_dir
        self.cwd = os.getcwd()

    def __enter__(self):
        os.chdir(self.target_dir)

    def __exit__(self, exc_type, exc_val, exc_tb):
        os.chdir(self.cwd)


def hash_return(local_file, hash_type='sha256'):
    """Return the hash of a local file object.

    This function will support any hash type available within ``hashlib``.

    :param local_file: ``str``
    :param hash_type: ``str``
    :return: ``str``
    """
    def calc_hash():
        """Read the hash.
        :return data_hash.read():
        """
        return file_object.read(128 * hash_function.block_size)

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
