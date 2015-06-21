Yet Another Python Repo Tool
############################
:date: 2013-09-05 09:51
:tags: python, github, pip, pypi
:category: \*nix


General Overview
----------------

Yaprt is a tool built to turn Python source code into a python wheels. While that not all that remarkable yaprt goes a bit further. The idea behind yaprt is to allow deployers to maintain lots of diverse projects in different repositories and turn source code into distributable python packages with minimal effort while maintaining dependencies and requirements across the various projects without finding duplicate packages and disjointed versions in what should be a stable deployment.

Yaprt has lots of functionality though has a simple cli interface. For everything yaprt can do please review ``yaprt --help``. Additionally all of the sub-commands have more information regarding options that are unique to the individual sub-command. These options can be viewed via ``yaprt sub-command --help``.


Example Usage
-------------

The commands listed regarding the functionality of yaprt assume that you will have the following directory structure created within your host.

.. code-block:: bash

    mkdir -p /var/www/repos/             ## Main repo directory
    mkdir -p /var/www/repos/os-releases  ## Location where symlinked wheels will exist
    mkdir -p /var/www/repos/pools        ## Location where wheels will exist
    mkdir -p /var/www/repos/reports/     ## Location where report files will exist
    mkdir -p /var/www/repos/repos-file   ## Location where requirement files will exist


In the basic example I'm going to assume that you have some ``repo_file.txt`` on your system and it has a bunch of git repos within it.  In my example I will be creating a report targeting OpenStack services and clients for the latest *stable/juno* and will create all of the python wheels for use in my local index.

.. code-block:: bash

    cat > /var/www/repos/repos-file/openstack-repos-file.txt<<EOF
    git+https://github.com/openstack/python-tuskarclient@0.1.8
    git+https://github.com/openstack/python-ceilometerclient@1.0.9
    git+https://github.com/openstack/oslo.middleware@0.4.0
    git+https://github.com/openstack/neutron@2014.2.2
    git+https://github.com/openstack/oslo.messaging@1.4.1
    git+https://github.com/openstack/python-heatclient@0.2.12
    git+https://github.com/openstack/python-keystoneclient@1.0.0
    git+https://github.com/openstack/glance_store@0.1.10
    git+https://github.com/openstack/tempest@3
    git+https://github.com/openstack/python-swiftclient@2.3.1
    git+https://github.com/openstack/python-openstackclient@1.0.1
    git+https://github.com/openstack/python-cinderclient@1.1.1
    git+https://github.com/openstack/cinder@2014.2.2
    git+https://github.com/openstack/python-saharaclient@0.7.6
    git+https://github.com/openstack/heat@2014.2.2#egg=extraroute&subdirectory=contrib/extraroute
    git+https://github.com/openstack/tempest@master
    git+https://github.com/openstack/python-novaclient@2.20.0
    git+https://github.com/openstack/horizon@2014.2.2
    git+https://github.com/openstack/swift@2.2.1
    git+https://github.com/openstack/python-ironicclient@0.2.1
    git+https://github.com/openstack/keystonemiddleware@1.3.1
    git+https://github.com/openstack/python-neutronclient@2.3.10
    git+https://github.com/openstack/glance@2014.2.2
    git+https://github.com/openstack/heat@2014.2.2
    git+https://github.com/openstack/python-troveclient@1.0.8
    git+https://github.com/openstack/python-barbicanclient@2.2.1
    git+https://github.com/openstack/requirements@stable/juno
    git+https://github.com/openstack/python-zaqarclient@0.1.0
    git+https://github.com/openstack/python-designateclient@1.0.3
    git+https://github.com/openstack/keystone@2014.2.2
    git+https://github.com/openstack/python-glanceclient@0.15.0
    git+https://github.com/openstack/nova@2014.2.2
    EOF

With this basic requirements file ready we feed that file into yaprt using the ``create-report`` sub-command which will kick out a JSON report file. The report file will list all of the discovered requirements and pip install URLs for the items I listed in the requirements file.

.. code-block:: bash

    yaprt create-report \
          --report-file /var/www/repos/reports/release-stable-juno-report.json \
          --git-install-repos-file /var/www/repos/repos-file/openstack-repos-file.txt


Now that the report file `/var/www/repos/reports/release-stable-juno-report.json` is ready its time to tell yaprt to build all of the python bits into python wheels.

Applying patches to a sources
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Yaprt can also use ref spec commits from things like gerrit and can chain multiple commits to gether to create a single patched branch. To do this you'd create an entry within the `repo_file.txt` or on the command line that looks like this:

.. code-block:: shell

    git+https://review.openstack.org/openstack/neutron@refs/changes/59/177159/12,refs/changes/11/187011/3,refs/changes/66/180466/2


This entry will base all commits at the point in time of the first refs change with the other comma delimited changes as a cherry-pick on top. This will create a single "patched" branch which will be noted within the repo build report as items that have been patched via yaprt. Be aware that when doing multiple patches one on-top of one another the pick strategy is to always use the first commit in the list as the base with everything else picked on top of it. This is done using the following git pick process ``git cherry-pick -x FETCH_HEAD``. If there is an error in picking the commits, the process will halt resulting in log output regarding what's broken and why.


Telling yaprt to ignore requirement indexing
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Yaprt can be told to ignore requirement indexing by simply adding the ``yaprtignorerequirements=true`` fragment to the online URL for the repo.

.. code-block:: shell

    git+https://github.com/openstack/tempest@352082ec9a6847727aa3eb79d3a8d9008cea54d4#yaprtignorerequirements=true


While this will build the wheel for the given package it will not index and enforce the package requirements onto the rest of the items being built.


Building the wheels
-------------------

First we tell yaprt to resolve the requirements by themselves. Yaprt uses a solver for all of the known requirements such that it will make sure that there are no conflicting dependencies for all of the items being built within the given report. This is especially useful when dealing with multiple projects that implement independent requirements that may be disjointed from one another and have limited information on specifically what items are absolutely required and which are not.

.. code-block:: bash

    yaprt build-wheels \
          --report-file "/var/www/repos/reports/release-stable-juno-report.json" \
          --storage-pool "/var/www/repos/pools" \
          --link-dir "/var/www/repos/os-releases/juno" \
          --pip-bulk-operation \
          --build-output "/tmp/openstack-wheel-output" \
          --build-dir "/tmp/openstack-builder" \
          --build-requirements

At the completion of this command you will have a release requirements txt file that can be used with pip elsewhere if the full build was ever to need to be reproduced in a different location. This plain requirements file will be located at ``/var/www/repos/os-releases/juno/build_reqs.txt``

With the requirements built we move on to building the main services. Notice in the next command we are not building the using a bulk operation and have instructed yaprt to not build the dependencies. The reason that we're not building the dependencies in this part is because we've already done it with the previous command.

At the completion of this command we will have a loaded PyPi index which will be available here: `/var/www/repos/pools`. Additionally we will have a link directory at `/var/www/repos/os-releases/juno` which contains symlinks pointing back to the python wheels that are now stored in our pools directory.  This structure allows you to point `pip` at your new PyPi repository or your links directory which will further allow you to install pre-built python wheels within your environment based on source code that you just specified in your `/var/www/repos/repos-file/openstack-repos-file.txt` file. This creates a stable release of Python wheels that can be used to ensure consistency within a deployment for its lifetime.

.. code-block:: bash

    yaprt build-wheels \
          --report-file "/var/www/repos/reports/release-stable-juno-report.json" \
          --storage-pool "/var/www/repos/pools" \
          --link-dir "/var/www/repos/os-releases/juno" \
          --pip-no-deps \
          --build-output "/tmp/openstack-wheel-output" \
          --build-dir "/tmp/openstack-builder" \
          --build-branches \
          --build-releases


If you are only building the wheels for a local system you can stop here. However, if you are building these wheels on a remote system and your hosting the index via some web server you can run one more yaprt command to create html indexes of all the files found within your repo structure.

.. code-block:: bash

    yaprt --quiet \
          create-html-indexes \
          --repo-dir "/var/www/repos"

Now your done.


For more information on how to setup pip to simply use your frozen repository of wheels or our PyPi index please have a look at the pip.conf.example file within this repository for ideas on how that can be done as well as review the online documentation on regarding setting up and using pip configuration files (https://pip.pypa.io/en/latest/user_guide.html#configuration).
