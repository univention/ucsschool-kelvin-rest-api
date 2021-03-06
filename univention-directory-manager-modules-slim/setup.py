# -*- coding: utf-8 -*-

#
# Use only Python 2 and 3 compatible code here!
#

#
# Install: pip3 install .
#

import os
import re
import sys
import tempfile

try:
    from urllib import urlretrieve  # py2
except ImportError:
    from urllib.request import urlretrieve  # py3

import setuptools

changelog_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "changelog")
chlog_regex = re.compile(r"^(?P<package>.+?) \((?P<version>.+?)\) \w+;")
PIP_FALLBACK_URL = (
    "https://raw.githubusercontent.com/univention/univention-corporate-server/4.4-1/management/"
    "univention-directory-manager-modules/debian/changelog"
)

# when installing using "setup.py install ." the directory is not changed, when using pip, work is done
# in /tmp
if not os.path.exists(changelog_path):
    _fp, changelog_path = tempfile.mkstemp()
    urlretrieve(PIP_FALLBACK_URL, changelog_path)  # nosec

with open(changelog_path) as fp:
    for line in fp:
        m = chlog_regex.match(line)
        if m:
            break
    else:
        print("Could not parse find package name and version in {}.".format(changelog_path))
        sys.exit(1)

with open("requirements.txt") as fp:
    requirements = fp.read().splitlines()

setuptools.setup(
    name=m.groupdict()["package"],
    version=m.groupdict()["version"],
    author="Univention GmbH",
    author_email="packages@univention.de",
    description="UDM Python modules",
    long_description="UDM Python modules",
    url="https://www.univention.de/",
    install_requires=requirements,
    packages=["univention.admin"],
    license="GNU Affero General Public License v3",
    classifiers=[
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU Affero General Public License v3",
    ],
)
