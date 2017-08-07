# -*- coding: utf-8 -*-
from setuptools import setup, find_packages


home_url = 'https://github.com/bachew/damnode/tree/master'
config = {
    'name': 'damnode',
    'version': '0.0.3dev',
    'description': 'Node.js in Python virtual environments',
    'long_description': 'Go to `project page <{}#damnode>`_ for more info.'.format(home_url),
    'license': 'MIT',
    'author': 'Chew Boon Aik',
    'author_email': 'bachew@gmail.com',
    'url': home_url,
    'download_url': 'https://github.com/bachew/damnode/archive/master.zip',
    'packages': find_packages('src'),
    'package_dir': {'': 'src'},
    'install_requires': [
        'appdirs>=1.4.0',
        'Click>=6.7',
        'requests>=2.17.3',
        'six>=1.10.0',
    ],
    'entry_points': {
        'console_scripts': [
            'damnode=damnode.cli:main',
        ],
    },
    'test_suite': 'test',
    'zip_safe': False,
    'classifiers': [
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 3',

        # Keep in sync with .travis.yml python versions
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',

        'Topic :: Software Development :: Build Tools',
        'Topic :: Utilities',

    ],
}
setup(**config)
