# -*- coding: utf-8 -*-
import appdirs
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

    def _cache_dir():
        app_name = osp.splitext(osp.basename(__file__))[0]
        app_author = app_name  # makes no sense to use my name
        return appdirs.user_cache_dir(app_name, app_name)

    DEFAULT_CACHE_DIR = _cache_dir()

    def __init__(self):
        self.verbose = False
        self.cache = True
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

        name = osp.basename(link)

        with self._ensure_cache_dir():
            cached_file = osp.join(self.cache_dir, name)

            if osp.isfile(cached_file):
                self.info('Using cached {!r}'.format(cached_file))
                yield cached_file
                return

            if osp.isfile(link):
                self.info('Copying {!r}'.format(link))
                shutil.copyfile(link, cached_file)
                shutil.copystat(link, cached_file)
                yield cached_file
                return

            temp_fd, temp_file = tempfile.mkstemp(prefix='{}.download-'.format(name),
                                                  dir=self.cache_dir)
            self.info('Downloading {!r}'.format(link))
            self.debug('Downloading to temp file {!r}'.format(temp_file))

            with open(temp_file, 'wb') as f:
                resp = requests.get(link, stream=True)

                for chunk in self._iter_resp_chunks(resp):
                    f.write(chunk)

            self.debug('Rename {!r} to {!r}'.format(temp_file, cached_file))
            os.rename(temp_file, cached_file)
            yield cached_file

    @contextmanager
    def _ensure_cache_dir(self):
        if self.cache:
            if not self.cache_dir:
                self.cache_dir = self.DEFAULT_CACHE_DIR

            try:
                os.makedirs(self.cache_dir)
            except EnvironmentError as e:
                if e.errno == errno.EEXIST:
                    pass
                else:
                    raise

            yield
            return

        orig_cache_dir = self.cache_dir
        self.cache_dir = tempfile.mkdtemp()
        try:
            yield
        finally:
            shutil.rmtree(self.cache_dir)
            self.cache_dir = orig_cache_dir

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
@click.option('-i', '--index',
              help='Node index directory or URL (default: {!r})'.format(Damnode.DEFAULT_INDEX_URL))
@click.option('--no-cache', is_flag=True,
              help='Do not cache downloads')
@click.option('--cache-dir',
              help='Directory to cache downloads (default: {!r})'.format(Damnode.DEFAULT_CACHE_DIR))
@click.argument('hint', required=False)
@click.pass_obj
def cli_install(damnode, index, no_cache, cache_dir, hint):
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
    damnode.index = index
    damnode.cache = not no_cache
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
