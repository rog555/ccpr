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
import os
import re
from setuptools import find_packages
from setuptools import setup


PACKAGE_DIR = os.path.abspath(os.path.dirname(__file__))


def read(*args):
    """Reads complete file contents."""
    return open(os.path.join(PACKAGE_DIR, *args)).read()


def get_version():
    """Reads the version from this module."""
    init = read('codecommit_cli', '__init__.py')
    return re.compile(
        r"""__version__ = ['"]([0-9.]+)['"]"""
    ).search(init).group(1)


def get_requirements():
    """Reads the requirements file."""
    requirements = read("requirements.txt")
    return list(requirements.strip().splitlines())


setup(
    name='ccpr',
    version=get_version(),
    description='AWS CodeCommit PR CLI',
    long_description=read('README.md'),
    long_description_content_type="text/markdown",
    author='Roger Foskett',
    author_email='r_foskett@hotmail.com',
    license='Apache License 2.0',
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent"
    ],
    install_requires=get_requirements(),
    entry_points={
        'console_scripts': [
            'ccpr = ccpr:cli',
        ]
    },
    url='https://github.com/rog555/codecommit-cli'
)
