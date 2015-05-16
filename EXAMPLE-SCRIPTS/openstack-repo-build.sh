#!/usr/bin/env bash
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

set -e -o -v

# Notes:
# This will build all the wheels for all the things.

# Trap any errors that might happen in executing the script
trap my_trap_handler ERR

# Ensure there is a base path loaded
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# Repositories
REPO_ACCOUNTS="${REPO_ACCOUNTS:-'https://api.github.com/orgs/openstack/repos'}"

# Additional repos that need building for our bits
FULL_REPOS="${FULL_REPOS:-''}"
if [ -z "${FULL_REPOS}" ];then
    FULL_REPOS="https://api.github.com/repos/cloudnull/cloudlib "
    FULL_REPOS+="https://api.github.com/repos/cloudnull/turbolift "
    FULL_REPOS+="https://api.github.com/repos/cloudnull/yaprt "
    FULL_REPOS+="https://api.github.com/repos/stackforge/os-ansible-deployment "
fi

# Defined variables
WORK_PATH="${WORK_PATH:-/var/www}"
POOL_PATH="${POOL_PATH:-${WORK_PATH}/repo/pools}"
LINKS_PATH="${LINKS_PATH:-${WORK_PATH}/repo/links}"
GIT_PATH="${GIT_PATH:-${WORK_PATH}/repo/repos}"
REPORTS_PATH="${REPORTS_PATH:-${WORK_PATH}/repo/reports}"
REPORT_JSON="${REPORT_JSON:-${REPORTS_PATH}/full-openstack-report.json}"

# Load any defaults if the file is found
if [ -f "/etc/default/py-repo-builder" ];then
    . /etc/default/py-repo-builder
fi

LOCKFILE="/tmp/wheel_builder.lock"

function my_trap_handler() {
    kill_job
}

function lock_file_remove() {
    if [ -f "${LOCKFILE}" ]; then
        rm "${LOCKFILE}"
    fi
}

function kill_job() {
    set +e
    # If the job needs killing kill the pid and unlock the file.
    if [ -f "${LOCKFILE}" ]; then
        PID="$(cat ${LOCKFILE})"
        lock_file_remove
        kill -9 "${PID}"
    fi
}

function cleanup() {
    # Ensure workspaces are cleaned up
    rm -rf /tmp/opc-wheel-output
    rm -rf /tmp/opc-builder
    rm -rf /tmp/opc_wheels*
    rm -rf /tmp/pip*
}

# Check for system lock file.
if [ ! -f "${LOCKFILE}" ]; then
    echo $$ | tee "${LOCKFILE}"
else
    if [ "$(find ${LOCKFILE} -mmin +240)" ]; then
        logger "Stale pid found for ${LOCKFILE}."
        logger "Killing any left over processes and unlocking"
        kill_job
    else
        NOTICE="Active job already in progress. Check pid \"$(cat ${LOCKFILE})\" for status. Lock file: ${LOCKFILE}"
        echo $NOTICE
        logger ${NOTICE}
        exit 1
    fi
fi

# Create report
yaprt create-report --repo-accounts "${REPO_ACCOUNTS}" \
                    --full-repos "${REPO_ACCOUNTS}" \
                    --report-file "${REPORT_JSON}"

# Build ALL wheels
yaprt build-wheels --report-file "${REPORT_JSON}" \
                   --build-output "/tmp/opc-wheel-output" \
                   --build-dir "/tmp/opc-builder" \
                   --link-dir "${LINKS_PATH}" \
                   --storage-pool "${POOL_PATH}" \
                   --build-releases \
                   --build-branches \
                   --build-requirements \
                   --disable-version-sanity

# Store ALL git repositories
yaprt store-repos --report-file "${REPORT_JSON}" \
                  --git-repo-path "${GIT_PATH}"

# Create HTML index pages everywhere
yaprt create-html-indexes --report-file "${REPORT_JSON}" \
                          --dir-exclude "${GIT_PATH}"

echo "Complete."

# Perform cleanup
cleanup

# Remove lock file on job completion
lock_file_remove
