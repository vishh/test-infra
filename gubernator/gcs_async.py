# Copyright 2016 The Kubernetes Authors All rights reserved.
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

import json
import logging
import urllib
import zlib

import google.appengine.ext.ndb as ndb


GCS_API_URL = 'https://storage.googleapis.com'
STORAGE_API_URL = 'https://www.googleapis.com/storage/v1/b'


@ndb.tasklet
def get(url):
    context = ndb.get_context()
    headers = {'accept-encoding': 'gzip, *', 'x-goog-api-version': '2'}
    for retry in xrange(6):
        result = yield context.urlfetch(url, headers=headers)
        status = result.status_code
        if status == 429 or 500 <= status < 600:
            yield ndb.sleep(2 ** retry)
            continue
        if status in (200, 206):
            content = result.content
            if result.headers.get('content-encoding') == 'gzip':
                content = zlib.decompress(result.content, 15 | 16)
            raise ndb.Return(content)
        logging.error("unable to fetch '%s': status code %d" % (url, status))
        raise ndb.Return(None)


def read(path):
    """
    Asynchronously reads a file from GCS.

    NOTE: for large files (>10MB), this may return a truncated response due to
    urlfetch API limits. We don't want to read large files currently, so this
    is not yet a problem.

    Args:
        path: the location of the object to read
    Returns:
        a Future that resolves to the file's data, or None if an error occurred.
    """
    url = GCS_API_URL + path
    return get(url)


@ndb.tasklet
def listdirs(path):
    """
    Asynchronously list directories present on GCS.

    NOTE: This returns at most 1000 results. The API supports pagination, but
    it's not implemented here.

    Args:
        path: the GCS bucket directory to list subdirectories of
    Returns:
        a Future that resolves to a list of directories, or None if an error
        occurred.
    """
    if path[-1] != '/':
        path += '/'
    assert path[0] != '/'
    bucket, prefix = path.split('/', 1)
    url = '%s/%s/o?delimiter=/&prefix=%s' % (STORAGE_API_URL, bucket, prefix)
    res = yield get(url)
    if res is None:
        raise ndb.Return(None)
    prefixes = json.loads(res).get('prefixes', [])
    raise ndb.Return(['%s/%s' % (bucket, prefix) for prefix in prefixes])

