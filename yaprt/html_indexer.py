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


"""Create an HTML index at the root of all directories recursively.

This module will create an HTML index as ``index.html`` in the root directory
of every directory found, recursively, within a given path.
"""

import base64
import os

from cloudlib import logger
import html

from yaprt import utils


LOG = logger.getLogger('repo_builder')


def return_hash(src_file):
    """Return a hash for a given file.

    :param src_file: Name of the file that will be hashed.
    :type src_file: ``str``
    :returns: ``str``
    """
    hash_sum = utils.hash_return(
        local_file=src_file,
        hash_type='md5'
    )
    if hash_sum:
        return base64.b64encode(hash_sum)


def create_html_indexes(args):
    """Create HTML indexes.

    The index.html file will be created within all folders of the `repo_dir`
    element of the *args* dict.

    :param args: Parsed arguments in dictionary format.
    :type args: ``dict``
    """
    full_path = utils.get_abs_path(file_name=args['repo_dir'])
    excludes = [utils.get_abs_path(file_name=i) for i in args['dir_exclude']]

    for fpath, afolders, afiles in os.walk(full_path):
        # Skip excluded directories.
        if [i for i in excludes if fpath.startswith(i)]:
            continue
        else:
            LOG.debug('Path Found: "%s"', fpath)
            _title = 'links for "%s"' % os.path.basename(fpath)
            index = html.HTML('html')
            head = index.head()
            head.title(_title)
            body = index.body(newlines=True)
            body.h1(_title)

            with utils.ChangeDir(fpath):
                LOG.debug('Folders Found: "%d"', len(afolders))
                for afolder in sorted(afolders):
                    full_folder_path = os.path.join(fpath, afolder)
                    body.a(
                        os.path.basename(full_folder_path),
                        href=os.path.relpath(full_folder_path),
                        rel="internal"
                    )
                    body.br()

                LOG.debug('Files Found: "%d"', len(afiles))
                for afile in sorted(afiles):
                    if afile == 'index.html':
                        continue

                    full_file_path = os.path.join(fpath, afile)
                    md5_hash = return_hash(full_file_path)
                    if md5_hash:
                        body.a(
                            os.path.basename(full_file_path).split('#')[0],
                            href=os.path.relpath(full_file_path),
                            rel="internal",
                            md='md5:%s' % md5_hash
                        )
                        body.br()
                    else:
                        os.remove(afile)
                else:
                    index_file = os.path.join(fpath, 'index.html')
                    with open(index_file, 'wb') as f:
                        f.write(str(index))
                    LOG.info('Index file [ %s ] created.', index_file)
