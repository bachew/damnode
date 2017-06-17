# -*- coding: utf-8 -*-
import click
import errno
import functools
import os
import platform
import re
import requests
import shutil
import six
import subprocess
import sys
import tempfile
import tarfile
from argparse import ArgumentParser
from cachecontrol import CacheControl  # TODO: not universal
from cachecontrol.caches.file_cache import FileCache
from click import BadParameter, ClickException, echo, ParamType
from collections import OrderedDict
from contextlib import contextmanager
from distutils import dir_util
from bs4 import BeautifulSoup
from os import path as osp
from six.moves.urllib import parse as urlparse
from subprocess import CalledProcessError
from zipfile import ZipFile


def _cached_property(method):
    @functools.wraps(method)
    def wrapped(self):
        key = '_{}'.format(method.__name__)

        if not hasattr(self, key):
            setattr(self, key, method(self))

        return getattr(self, key)

    return property(wrapped)


class DamNode(object):
    index_url = 'https://nodejs.org/dist/'
    min_version = (4, 0, 0)
    chunk_size = 1024 * 10
    node_dir = osp.join(osp.dirname(__file__), 'node')

    def __init__(self, **kwargs):
        for k, v in six.iteritems(kwargs):
            getattr(self, k)
            setattr(self, k, v)

    @property
    def session(self):
        if not getattr(self, '_session', None):
            cache_dir = osp.expanduser('~/.cache/damnode/requests')
            cache = FileCache(cache_dir)
            self._session = CacheControl(requests.Session(), cache=cache)

        return self._session

    def http_get(self, url, **kwargs):
        echo('GET {}'.format(url))  # TODO: option to turn off
        return self.session.get(url, **kwargs)

    def get_url_dict(self, url, parse_title, ignore_parse_error=True):
        resp = self.http_get(url)
        soup = BeautifulSoup(resp.text, 'html.parser')
        dct = OrderedDict()

        for link in soup.find_all('a'):
            title = link.string.strip()
            try:
                key = parse_title(title)
            except ValueError:
                if not ignore_parse_error:
                    raise
            else:
                href = link.attrs.get('href').strip()

                if href:
                    dct[key] = urlparse.urljoin(resp.url, href)

        return dct

    @_cached_property
    def version_url_dict(self):

        def parse_title(title):
            ver = _parse_version(title, suffix='/?$')

            if ver < self.min_version:
                raise ValueError

            return ver

        return self.get_url_dict(self.index_url, parse_title)

    def get_package_url_dict(self, version_url):
        return self.get_url_dict(version_url, self.parse_package_title)

    def parse_package_title(self, title):
        m = re.match(r'^node-v[^-]+-(?P<platf>[^-]+)-(?P<arch>[^\.]+).(?P<fmt>.*)$', title)

        if not m:
            raise ValueError

        return m.group('platf'), m.group('arch'), m.group('fmt')

    def find_version_url(self, version):
        def version_match(actual_ver, ver):
            if not ver:
                return True

            if not self.match(actual_ver[0], ver[0]):
                return False

            if not self.match(actual_ver[1], ver[1]):
                return False

            return self.match(actual_ver[2], ver[2])

        ver_url_dict = self.version_url_dict

        for actual_version in reversed(sorted(six.iterkeys(ver_url_dict))):
            if version_match(actual_version, version):
                return ver_url_dict[actual_version]

        return None

    def iter_package_urls(self, version_url, platf, arch, fmt):
        pkg_url_dict = self.get_package_url_dict(version_url)

        for (actual_platf, actual_arch, actual_fmt), pkg_url in six.iteritems(pkg_url_dict):
            if self.match(actual_platf, platf) and self.match(actual_arch, arch) and self.match(actual_fmt, fmt):
                yield pkg_url

    def match(self, actual_val, val):
        return not val or val == actual_val

    def detect_platf(self):
        mapping = [
            (r'^windows$', 'win'),
            # TODO: aix, sunos
        ]
        value = platform.system().lower()
        return self.map(mapping, value)

    def detect_arch(self):
        mapping = [
            (r'^x86[^\d]64$', 'x64'),
            (r'^amd64$', 'x64'),
            (r'^x86[^\d]', 'x86'),
            # TODO: arm64, armv6l, armv7l, ppc64, ppc64le, s390x
        ]
        value = platform.machine().lower()
        return self.map(mapping, value)

    def detect_fmt(self, platf):
        return 'zip' if platf == 'win' else 'tar.gz'

    def map(self, mapping, value):
        for pattern, value2 in mapping:
            if re.match(pattern, value):
                return value2

        return value

    @contextmanager
    def download_package(self, pkg_url):
        # TODO: verify checksum
        filename = osp.basename(urlparse.urlparse(pkg_url).path)

        with self.download_file(pkg_url) as path:
            yield path

    @contextmanager
    def download_file(self, url):
        resp = self.http_get(url, stream=True)
        total_size = resp.headers.get('content-length')

        with _temp_dir() as tdir:
            path = osp.join(tdir, osp.basename(url))
            content_length = int(resp.headers['content-length'])

            with open(path, 'wb') as f, click.progressbar(length=content_length) as progress:
                for chunk in resp.iter_content(chunk_size=self.chunk_size):
                    f.write(chunk)
                    progress.update(self.chunk_size)

            yield path

    def install_package(self, package_file):
        echo('Installing {!r} into {!r}'.format(package_file, self.node_dir))

        with _temp_dir() as tdir:
            if package_file.endswith('.tar.gz'):  # tar.gz
                with tarfile.open(package_file, 'r|gz') as tar_file:
                    # tar_file.extractall(tdir)

                    # TESTING
                    first_dir = osp.basename(package_file[:-7])
                    echo('first_dir: {!r}'.format(first_dir))

                    for member in tar_file:
                        member.name = osp.relpath(member.name, first_dir)
                        echo('extract {} -> {}'.format(member.name, sys.prefix))
                        tar_file.extract(member, sys.prefix)
            elif package_file.endswith('.zip'):
                with ZipFile(package_file, 'r') as zip_file:
                    zip_file.extractall(tdir)
            else:
                raise NotImplementedError('File format not supported: {}'.format(osp.basename(package_file)))

            extracted_node_dir = osp.join(tdir, os.listdir(tdir)[0])

            # _rmtree(self.node_dir)
            # shutil.move(extracted_node_dir, sys.prefix)

    @property
    def installed(self):
        return osp.exists(self.node_dir)


class DamNodeError(ClickException):
    pass


class VersionType(ParamType):
    name = 'version'

    def convert(self, value, param, ctx):
        return _parse_version(value)


def install(args):
    cmd_install(args, standalone_mode=False)


def uninstall(args):
    cmd_uninstall(args, standalone_mode=False)


def nrun(args):
    cmd_nrun(args, standalone_mode=False)


def node(args):
    nrun(['node'] + list(args))


def npm(args):
    nrun(['npm'] + list(args))


@click.group()
@click.help_option('-h', '--help')
def cmd_main():
    pass


@cmd_main.command('install')
@click.option('-p', '--platform', 'platf',
              help='E.g. darwin, linux, win (default: current platform)')
@click.option('-a', '--architecture', 'arch',
              help='E.g. arm64, x64, x86 (default: current architecture)')
@click.option('-f', '--format', 'fmt',
              help="E.g. tar.gz, zip (default: platform's preferred format)")
@click.option('--detect/--no-detect', 'detect',
              default=True,
              help='Detect platform, architecture and format (default: true)')
@click.option('--list-versions', is_flag=True,
              help='List available versions')
@click.help_option('-h', '--help')
@click.argument('version',
                 required=False,
                 type=VersionType())
def cmd_install(platf, arch, fmt, detect, version, list_versions):
    '''
    Install Node

    VERSION can be full (e.g. 8.0.0) or partial (e.g. 7.10, v6), latest
    version will be installed if it's partial.
    '''
    damn = DamNode()

    if list_versions:
        for ver in reversed(sorted(damn.version_url_dict.keys())):  # TODO: damn.versions
            echo('.'.join([str(n) for n in ver]))  # TODO: format_version()
        return

    if damn.installed:
        raise DamNodeError("Node is already installed, you can uninstall it by running 'damnode uninstall'")

    if platf is None and detect:
        platf = damn.detect_platf()

    if arch is None and detect:
        arch = damn.detect_arch()

    if fmt is None and detect:
        fmt = damn.detect_fmt(platf)

    version_url = damn.find_version_url(version)

    if not version_url:
        raise DamNodeError("Could not find the version specified, please run 'damnode install --list-versions' to see versions available")

    package_urls = list(damn.iter_package_urls(version_url, platf, arch, fmt))

    if not package_urls:
        version_str = ' {}'.format(version) if version else ''  # TODO: format_version()
        raise DamNodeError((
            "Could not find package for {}-{} in {} format"
            ", please run \"damnode install -p '' -a '' -f ''{}\" to see why").format(platf, arch, fmt, version_str))

    if len(package_urls) > 1:
        msg = ['More than one package found:']

        for url in package_urls:
            msg.append('\n  ')
            msg.append(url)

        raise DamNodeError(''.join(msg))

    with damn.download_package(package_urls[0]) as package_file:
        damn.install_package(package_file)

    # To prevent warning: "npm is using <node>/bin/node but there is no node binary in the current PATH"
    nrun(['npm', 'config', 'set', 'scripts-prepend-node-path', 'false'])


@cmd_main.command('uninstall')
@click.option('--yes', is_flag=True, help='Confirm uninstallation')
@click.help_option('-h', '--help')
def cmd_uninstall(yes):
    '''
    Uninstall Node.
    '''
    damn = DamNode()

    if not yes:
        click.confirm('This will remove {!r}, are you sure?'.format(damn.node_dir, abort=True))

    _rmtree(damn.node_dir)
    echo('{!r} removed'.format(damn.node_dir))


@click.command(context_settings=dict(ignore_unknown_options=True))
@click.help_option('-h', '--help')
@click.option('-g', 'use_global', is_flag=True, help='Include global node_modules')
@click.argument('node_bin', nargs=-1, type=click.UNPROCESSED)
def cmd_nrun(use_global, node_bin):
    damn = DamNode()

    if not damn.installed:
        raise DamNodeError("Node is not yet installed, run 'damnode install' to install it")

    # FIXME: No bin directory on Windows zip
    bin_dir = osp.join(damn.node_dir, 'bin')

    if not node_bin:
        msg = [
            'node_bin is required\n',
            'Please specified one:'
        ]

        for bin_name in os.listdir(bin_dir):
            msg.append('\n  ')
            msg.append(bin_name)

        raise click.BadParameter(''.join(msg))

    # TODO: ./node_modules/*/bin

    cmd = [osp.join(bin_dir, node_bin[0])]
    cmd.extend(node_bin[1:])

    env = None

    if use_global:
        env = {
            'NODE_PATH': osp.join(damn.node_dir, 'lib/node_modules')
        }

    try:
        subprocess.check_call(cmd, env=env)
    # TODO: handle ENOENT, print list like missing node_bin
    except CalledProcessError as e:
        # TODO: raise SystemExit(e.returncode) if standalone_mode
        cmdline = subprocess.list2cmdline(cmd)
        e2 = ClickException('{!r} failed with exit code {!r}'.format(cmdline, e.returncode))
        e2.exit_code = e.returncode
        raise e2


def cmd_node():
    cmd_nrun(['node'] + sys.argv[1:])


def cmd_npm():
    cmd_nrun(['npm'] + sys.argv[1:])


def _parse_version(ver_str, prefix=r'^', suffix=r'$'):
    pattern = prefix + r'v?(?P<major>\d+)(\.(?P<minor>\d+))?(\.(?P<build>\d+))?' + suffix
    m = re.match(pattern, ver_str)

    if not m:
        raise ValueError('Must match {}'.format(pattern))

    opt_int = lambda s: None if s is None else int(s)
    return int(m.group('major')), opt_int(m.group('minor')), opt_int(m.group('build'))


@contextmanager
def _temp_dir():
    dirname = tempfile.mkdtemp()
    try:
        yield dirname
    finally:
        _rmtree(dirname)


def _rmtree(path):
    try:
        shutil.rmtree(path)
    except OSError as e:
        if e.errno == errno.ENOENT:
            pass  # does not exist
        else:
            raise


if __name__ == '__main__':
    cmd_main()
