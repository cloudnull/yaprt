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

"""Repository build tool.

The idea behind this tool is to provide for an application that can build a
repository of python wheels in a format that is pypi index capable, can be used
as a pool of links, and resolves dependencies and dependent versions when
duplicate packages are marked for building.

This tool can:
    * Build reports from information obtained using the github api about
      specific repositories and or from the repositories of an entire account.
      When scanning through the repositories, any repo with a
      `requirements.txt` and or a `setup.py` file with the discovered path will
      be added into the report as a list of requirements and or installable
      URLs on a per branch basis. Also any thing that has been tagged within a
      project will be listed in the report.
    * Build the python wheels from a "pre-built" report or via input on the
      CLI. If user input can also be added to an existing report which can be
      used to modify or add to the build requirements. When the wheels are
      built the structure will consist of the repository directory indexing,
      a links directory, and an option "release" directory.
    * Store the git sources from the report into a specific location. If the
      source code already exists within the targeted location the git repo will
      be updated with any changes that may have been made upstream.
    * Create a static html index for all files within a directory. Because
      this is a recursive function, each index will be created within the
      directory and only reference files within that directory.
"""


from cloudlib import arguments
from cloudlib import indicator
from cloudlib import logger

import yaprt


def _importer(module, method):
    """Returns a method from an imported module.

    :param module: String name of the module to import. This should be in
                   dotted notation.
    :type module: ``str``
    :param method: Name of the method to return.
    :type method: ``str``
    :returns: ``object``
    """
    module_object = getattr(
        __import__(module, fromlist=list()),
        module.split('.')[-1]
    )
    return getattr(module_object, method)


def _arguments():
    """Return CLI arguments."""
    return arguments.ArgumentParserator(
        arguments_dict=yaprt.ARGUMENTS_DICT,
        epilog='Licensed Apache2',
        title='Python package builder Licensed "Apache 2.0"',
        detail='Openstack package builder',
        description='Rackspace Openstack, Python wheel builder',
        env_name='OS_REPO'
    ).arg_parser()


def preload_for_main():
    """Return arguments dict, sinner bol, and logging object."""
    args = _arguments()

    # set boolean objects for spinner and stream logging.
    if args['debug'] is True:
        run_spinner = False
        stream_logs = True
    elif args['quiet'] is True:
        run_spinner = False
        stream_logs = False
    else:
        run_spinner = True
        stream_logs = False

    # Load the logging.
    _logging = logger.LogSetup(debug_logging=args['debug'])
    log = _logging.default_logger(
        name='repo_builder',
        enable_stream=stream_logs
    )

    return args, run_spinner, log


def main():
    """Run the main application."""
    args, run_spinner, log = preload_for_main()
    with indicator.Spinner(run=run_spinner):
        if args['parsed_command'] == 'create-report':
            action = _importer('yaprt.packaging_report', 'create_report')
        elif args['parsed_command'] == 'store-repos':
            action = _importer('yaprt.clone_repos', 'store_repos')
        elif args['parsed_command'] == 'build-wheels':
            action = _importer('yaprt.wheel_builder', 'build_wheels')
        elif args['parsed_command'] == 'create-html-indexes':
            action = _importer('yaprt.html_indexer', 'create_html_indexes')
        else:
            # This is imported here because its not used unless there is an
            # error. If imported above, this caused a double log entry.
            from yaprt import utils
            raise utils.AError(
                'No known parsed command, Current Args: "%s"', args
            )

        # Run the action
        action(args=args)

if __name__ == '__main__':
    main()
