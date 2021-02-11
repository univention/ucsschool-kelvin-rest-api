# -*- coding: utf-8 -*-

# Copyright 2020-2021 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <http://www.gnu.org/licenses/>.


#
# Install: python3 -m pip install -e .
#

import os
import shutil
from pathlib import Path
from subprocess import check_call
from typing import Iterable

import setuptools

with (Path(__file__).parent / "requirements.txt").open("r") as fp:
    requirements = fp.read().splitlines()

with (Path(__file__).parent / "requirements_dev.txt").open("r") as fp:
    requirements_dev = fp.read().splitlines()

with (Path(__file__).parent / "requirements_test.txt").open("r") as fp:
    requirements_test = fp.read().splitlines()

with (Path(__file__).parent / "VERSION.txt").open("r") as fp:
    version = fp.read().strip()


class BuildHTMLCommand(setuptools.Command):
    description = "generate HTML from RST"
    user_options = [("input-file=", "i", "input file")]

    def initialize_options(self):
        self.input_file = None

    def finalize_options(self):
        pass

    def run(self):
        for name in ("rst2html5.py", "rst2html5-3.py", "rst2html5", "rst2html5-3"):
            rst2_html5_exe = shutil.which(name)
            if rst2_html5_exe:
                break
        else:
            raise RuntimeError("Cannot find 'rst2html5'.")
        if self.input_file:
            target_dir = Path(self.input_file).parent / "static"
            if not target_dir.exists():
                print(f"mkdir -p {target_dir!s}")
                target_dir.mkdir(parents=True)
            target_file = target_dir / f"{str(Path(self.input_file).name)[:-3]}html"
            self.check_call([rst2_html5_exe, self.input_file, str(target_file)])
        else:
            for entry in self.recursive_scandir(Path(__file__).parent):
                if entry.is_file() and entry.name.endswith(".rst"):
                    target_dir = Path(entry.path).parent / "static"
                    if not target_dir.exists():
                        print(f"mkdir -p {target_dir!s}")
                        target_dir.mkdir(parents=True)
                    target_file = target_dir / f"{str(entry.name)[:-3]}html"
                    self.check_call([rst2_html5_exe, entry.path, str(target_file)])

    @classmethod
    def recursive_scandir(cls, path: Path) -> Iterable[os.DirEntry]:
        for entry in os.scandir(path):
            if entry.is_dir(follow_symlinks=False):
                yield from cls.recursive_scandir(entry.path)
            yield entry

    @classmethod
    def check_call(cls, cmd):
        print(f"Executing: {cmd!r}")
        check_call(cmd)


setuptools.setup(
    name="ucs-school-kelvin-api",
    version=version,
    author="Univention GmbH",
    author_email="packages@univention.de",
    description="UCS@school Kelvin REST API",
    long_description="UCS@school Kelvin REST API",
    url="https://www.univention.de/",
    install_requires=requirements,
    setup_requires=["docutils", "pytest-runner"],
    tests_require=requirements_test,
    extras_require={
        "development": set(requirements + requirements_dev + requirements_test)
    },
    packages=["ucsschool.kelvin", "ucsschool.kelvin.routers"],
    python_requires=">=3.7",
    license="GNU Affero General Public License v3",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Framework :: AsyncIO",
        "Intended Audience :: Information Technology",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: HTTP Servers",
    ],
    cmdclass={"build_html": BuildHTMLCommand},
)
