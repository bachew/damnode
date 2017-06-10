# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import re
import subprocess
import textwrap
import time
from os import path as osp
from setuptools import setup


def main():
    brtag = get_branch_or_tag()
    readme = split_readme()
    home_url = 'https://github.com/bachew/damnode/tree/{}'.format(brtag)
    go_home = textwrap.dedent('''\n
        Go to `project page <{}#damnode>`_ for more info.
        '''.format(home_url))
    config = {
        'name': 'damnode',
        'version': get_version(),
        'description': readme[2],
        'long_description': readme[3] + go_home,
        'license': 'MIT',
        'author': 'Chew Boon Aik',
        'author_email': 'bachew@gmail.com',
        'url': home_url,
        'download_url': 'https://github.com/bachew/damnode/archive/{}.zip'.format(brtag),

        'py_modules': ['damnode'],
        'setup_requires': [
            'wheel',
        ],
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
                'damn=damnode:cmd_main',
                'nrun=damnode:cmd_nrun',
                'node=damnode:cmd_node',
                'npm=damnode:cmd_npm',
            ],
        },
        'test_suite': 'testdamnode',
        'zip_safe': False,
        'classifiers': [
            'Development Status :: 3 - Alpha',
            'Environment :: Console',
            'Intended Audience :: Developers',
            'License :: OSI Approved :: MIT License',
            'Operating System :: OS Independent',
            'Programming Language :: Python :: 2',
            'Programming Language :: Python :: 2.7',
            'Programming Language :: Python :: 3',
            'Programming Language :: Python :: 3.3',
            'Programming Language :: Python :: 3.4',
            'Programming Language :: Python :: 3.5',
            'Programming Language :: Python :: 3.6',
            'Topic :: Software Development :: Build Tools',
            'Topic :: Utilities',

        ],
    }
    setup(**config)



def get_branch_or_tag():
    value = os.environ.get('TRAVIS_TAG') or os.environ.get('TRAVIS_BRANCH')

    if not value:
        value = subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD']).strip()

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
        readme = f.read().replace('\r', '')

    parts = re.split(r'\n{2,}', readme)
    solid_parts = []

    for part in parts:
        part = part.strip()

        if part:
            solid_parts.append(part)

    return solid_parts


if __name__ == '__main__':
    main()
