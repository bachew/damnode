# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import re
import textwrap
import time
from os import path as osp
from setuptools import setup


def main():
    brtag = get_branch_or_tag()
    version = get_version()

    print('brtag:', brtag)
    print('version:', version)

    readme = split_readme()
    home_url = 'https://github.com/bachew/damnode/tree/{}'.format(brtag)
    go_home = textwrap.dedent('''\n
        Go to `home page <{}>`_ for documentation.
        '''.format(home_url))
    config = {
        'name': 'damnode',
        'version': version,
        'description': readme[1],
        'long_description': readme[2] + go_home,
        'license': 'MIT',
        'author': 'Chew Boon Aik',
        'author_email': 'bachew@gmail.com',
        'url': home_url,
        'download_url': 'https://github.com/bachew/damnode/archive/{}.zip'.format(brtag),

        'py_modules': ['damnode'],
        'install_requires': [
            'beautifulsoup4',
            'cachecontrol[filecache]',
            'Click>=6.7,<7',
            'pathlib2',
            'requests',
            'six',
        ],
        'entry_points': {
            'console_scripts': [
                'damnode=damnode:cli',
                'node=damnode:node',
                'npm=damnode:npm',
            ],
        },
        'test_suite': 'testdamnode',
        'zip_safe': False,
        'classifiers': [
            'Development Status :: 4 - Beta',
            'Environment :: Console',
            'Intended Audience :: Developers',
            'License :: OSI Approved :: MIT License',
            'Operating System :: OS Independent',
            'Programming Language :: Python :: 2.7',
            'Programming Language :: Python :: 3',
            'Topic :: Software Development :: Build Tools',
            'Topic :: Utilities',

        ],
    }
    setup(**config)



def get_branch_or_tag():
    value = os.environ.get('TRAVIS_TAG') or os.environ.get('TRAVIS_BRANCH')

    if not value:
        raise RuntimeError('Either TRAVIS_TAG or TRAVIS_BRANCH must be set')

    return value


def get_version():
    tag = os.environ.get('TRAVIS_TAG')

    if tag:
        return tag

    dev_num = os.environ.get('TRAVIS_BUILD_ID') or int(time.time())
    return '0.dev{}'.format(dev_num)


def split_readme():
    base_dir = osp.abspath(osp.dirname(__file__))
    readme_file = osp.join(base_dir, 'README.md')

    with open(readme_file) as f:
        readme = f.read()

    if '\r' in readme:
        raise RuntimeError(r'{!r} contains {!r}'.format(readme_file, '\r'))

    parts = re.split(r'\n{2,}', readme)
    solid_parts = []

    for part in parts:
        part = part.strip()

        if part:
            solid_parts.append(part)

    return solid_parts


if __name__ == '__main__':
    main()
