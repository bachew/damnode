# -*- coding: utf-8 -*-
import click
import errno
import os
import re
import requests
import traceback
from click import ClickException
from os import path as osp
from six.moves.html_parser import HTMLParser
from six.moves.urllib import parse as urlparse


class Damnode(object):
    DEFAULT_INDEX_URL = 'https://nodejs.org/dist/'
    KNOWN_PACKAGE_SUFFIXES = [
        '.gz',
        '.msi',
        '.pkg',
        '.xz',
        '.zip',
    ]

    def __init__(self):
        self.verbose = False
        self.cache_dir = None

    def info(self, msg):
        click.echo(str(msg))

    def debug(self, msg):
        if self.verbose:
            self.info('DEBUG: {}'.format(msg))

    def install(self, hint):
        self.info("Let's install {}!".format(hint))

    def uninstall(self):
        self.info('TODO')

    def list_index(self, index):
        for suffix in self.KNOWN_PACKAGE_SUFFIXES:
            if index.endswith(suffix):
                raise ValueError('{!r} is a package, not an index'.format(index))

        try:
            entries = os.listdir(index)
        except EnvironmentError as e:
            if e.errno in (errno.ENOENT, errno.ENOTDIR):
                pass
            else:
                raise
        else:
            return sorted([osp.join(index, e) for e in entries])

        list_html = lambda h: IndexHtmlParser(index, h).entries

        try:
            with open(index, 'r') as f:
                html = f.read()
        except EnvironmentError as e:
            if e.errno  == errno.ENOENT:
                pass
            else:
                raise
        else:
            return sorted(list_html(html))

        resp = requests.get(index)
        return sorted(list_html(resp.text))


class IndexHtmlParser(HTMLParser):
    def __init__(self, url, html):
        HTMLParser.__init__(self)
        self.entries = []
        self.url = url
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag.lower() != 'a':
            return

        for name, value in attrs:
            if name.lower() != 'href':
                continue

            value = value.strip()

            if not value:
                continue

            path = urlparse.urljoin(self.url, value)
            self.entries.append(path)


class DamnodeCommand(click.Group):
    def invoke(self, ctx):
        damnode = Damnode()
        ctx.obj = damnode
        try:
            return super(DamnodeCommand, self).invoke(ctx)
        except (ClickException, click.Abort):
            raise
        except Exception as e:
            if damnode.verbose:
                traceback.print_exc()
                raise
            else:
                raise ClickException(str(e))


@click.command(cls=DamnodeCommand)
@click.help_option('-h', '--help')
@click.option('-v', '--verbose',
              is_flag=True,
              default=False,
              help='Verbose output')
@click.pass_obj
def cli(damnode, verbose):
    damnode.verbose = verbose


@cli.command('install')
@click.help_option('-h', '--help')
@click.option('-i', '--index-url', help='Node index URL (default: {})'.format(Damnode.DEFAULT_INDEX_URL))
@click.option('-c', '--cache-dir', help='Directory to cache downloads (default: no cache)')
@click.argument('hint', required=False)
@click.pass_obj
def cli_install(damnode, index_url, cache_dir, hint):
    '''
    Install Node of latest version or from the given HINT, it is detected as follows:

    \b
    1. Package URL (e.g. https://nodejs.org/dist/v4.8.3/node-v4.8.3-linux-x64.tar.gz)
    2. Version URL (e.g. https://nodejs.org/dist/v5.12.0/)
    2. Package filename (e.g. ~/Downloads/node-v6.11.0-darwin-x64.tar.gz)
    3. Exact version (e.g. 7.9.0, v7.10.0), v doesn't matter
    4. Partial version (e.g. v8, 8.1), latest version will be selected
    5. LTS name (e.g. argon, Boron), case insensitive

    Only tar.gz and zip formats are supported.
    '''
    damnode.index_url = index_url
    damnode.cache_dir = cache_dir
    damnode.install(hint)


@cli.command('uninstall')
@click.help_option('-h', '--help')
@click.confirmation_option('--yes',
                           help='Confirm uninstallation',
                           prompt='This will remove Node and only its bundled node_modules, continue?')
@click.pass_obj
def cli_uninstall(damnode):
    damnode.uninstall()
