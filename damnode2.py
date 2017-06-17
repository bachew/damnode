# -*- coding: utf-8 -*-
import click
import errno
import os
import re
import requests
import shutil
import tempfile
import traceback
from click import ClickException
from contextlib import contextmanager
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
    DOWNLOAD_CHUNK_SIZE = 10 * 1024

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

    def read_links(self, link):
        if self.is_package(link):
            raise ValueError('{!r} is a package, does not have links'.format(link))

        self.info('Reading links from {!r}'.format(link))

        try:
            entries = os.listdir(link)
        except EnvironmentError as e:
            if e.errno in (errno.ENOENT, errno.ENOTDIR):
                pass
            else:
                raise
        else:
            return sorted([osp.join(link, e) for e in entries])

        read_html = lambda h: HtmlLinksParser(link, h).links

        try:
            with open(link, 'r') as f:
                html = f.read()
        except EnvironmentError as e:
            if e.errno  == errno.ENOENT:
                pass
            else:
                raise
        else:
            return sorted(read_html(html))

        resp = requests.get(link)
        return sorted(read_html(resp.text))

    def is_package(self, link):
        for suffix in self.KNOWN_PACKAGE_SUFFIXES:
            if link.endswith(suffix):
                return True

        return False

    @contextmanager
    def download(self, link):
        if not self.is_package(link):
            raise ValueError('{!r} is not a package and cannot be downloaded'.format(link))

        if osp.isfile(link):
            yield link
            return

        name = osp.basename(link)

        if self.cache_dir:
            cached_file = osp.join(self.cache_dir, name)

            if osp.isfile(cached_file):
                self.info('Using cached {!r}'.format(cached_file))
                yield cached_file
                return

        self.info('Downloading {!r}'.format(link))
        resp = requests.get(link, stream=True)

        with self._ensure_cache_dir() as cache_dir:
            fd, tfile = tempfile.mkstemp(prefix='{}.download-'.format(name), dir=cache_dir)
            self.debug('Downloading to temp file {!r}'.format(tfile))

            with open(tfile, 'wb') as f:
                for chunk in self._iter_resp_chunks(resp):
                    f.write(chunk)

            final_file = osp.join(cache_dir, name)
            self.debug('Rename {!r} to {!r}'.format(tfile, final_file))
            os.rename(tfile, final_file)
            yield final_file

    @contextmanager
    def _ensure_cache_dir(self):
        if self.cache_dir:
            try:
                os.makedirs(self.cache_dir)
            except EnvironmentError as e:
                if e.errno == errno.EEXIST:
                    pass
                else:
                    raise
            yield self.cache_dir
            return

        tdir = tempfile.mkdtemp()
        try:
            yield tdir
        finally:
            shutil.rmtree(tdir)

    def _iter_resp_chunks(self, resp):
        chunk_size = self.DOWNLOAD_CHUNK_SIZE
        try:
            content_length = int(resp.headers.get('content-length', ''))
        except ValueError:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                yield chunk
        else:
            # Got Content-Length, show progress bar
            with click.progressbar(length=content_length) as progress:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    yield chunk
                    progress.update(chunk_size)


class HtmlLinksParser(HTMLParser):
    def __init__(self, url, html):
        HTMLParser.__init__(self)
        self.links = []
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
            self.links.append(path)


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
    1. Exact version (e.g. 7.9.0, v7.10.0), v doesn't matter
    2. Partial version (e.g. v8, 8.1), latest version will be selected
    3. Package file (e.g. ~/Downloads/node-v6.11.0-darwin-x64.tar.gz)
    4. Package URL (e.g. https://nodejs.org/dist/v4.8.3/node-v4.8.3-linux-x64.tar.gz)
    5. Packages directory (e.g. /var/www/html/node/v5.12.0/)
    6. Version URL (e.g. https://nodejs.org/dist/v5.12.0/)
    7. LTS name (e.g. argon, Boron), case insensitive

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
