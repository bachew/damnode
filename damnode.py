# -*- coding: utf-8 -*-
import click
import errno
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
from cachecontrol import CacheControl
from cachecontrol.caches.file_cache import FileCache
from collections import OrderedDict
from contextlib import contextmanager
from bs4 import BeautifulSoup
from os import path as osp
from pathlib2 import Path
from six.moves.urllib import parse as urlparse
from zipfile import ZipFile


class DamNode(object):
    index_url = 'https://nodejs.org/dist/'
    min_version = (4, 0, 0)
    chunk_size = 1024 * 10
    node_dir = Path(__file__).parent / 'node'

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
        click.echo('GET {}'.format(url))
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

    def get_version_url_dict(self):

        def parse_title(title):
            ver = parse_version(title, suffix='/?$')

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

    def iter_packages(self, ver, platf, arch, fmt):
        def version_match(actual_ver, ver):
            if ver is None:
                return True

            if not match(actual_ver[0], ver[0]):
                return False

            if not match(actual_ver[1], ver[1]):
                return False

            return match(actual_ver[2], ver[2])

        def match(actual_val, val):
            return val is None or val == actual_val

        ver_url_dict = self.get_version_url_dict()

        for actual_ver in reversed(sorted(six.iterkeys(ver_url_dict))):
            if version_match(actual_ver, ver):
                ver_url = ver_url_dict[actual_ver]
                pkg_url_dict = self.get_package_url_dict(ver_url)

                for (actual_platf, actual_arch, actual_fmt), pkg_url in six.iteritems(pkg_url_dict):
                    if match(actual_platf, platf) and match(actual_arch, arch) and match(actual_fmt, fmt):
                        yield pkg_url, actual_platf, actual_arch, actual_fmt
                break

    def detect_platf_arch_fmt(self):
        return self.detect_platf(), self.detect_arch(), self.detect_fmt()

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

    def detect_fmt(self):
        return 'zip' if self.detect_platf() == 'win' else 'tar.gz'

    def map(self, mapping, value):
        for pattern, value2 in mapping:
            if re.match(pattern, value):
                return value2

        return value

    @contextmanager
    def download_package(self, pkg_url):
        # TODO: verify checksum
        filename = Path(urlparse.urlparse(pkg_url).path).name

        with self.download_file(pkg_url) as path:
            yield path

    @contextmanager
    def download_file(self, url):
        resp = self.http_get(url, stream=True)
        total_size = resp.headers.get('content-length')

        with _temp_dir() as tdir:
            path = tdir / Path(url).name
            content_length = int(resp.headers['content-length'])

            with open(str(path), 'wb') as f, click.progressbar(length=content_length) as progress:
                for chunk in resp.iter_content(chunk_size=self.chunk_size):
                    f.write(chunk)
                    progress.update(self.chunk_size)

            yield path

    def install_package(self, pkg_file):
        pkg_file = Path(pkg_file)
        click.echo('Installing {!r} into {!r}'.format(str(pkg_file), str(self.node_dir)))

        with _temp_dir() as tdir:
            if pkg_file.suffix == '.gz':  # tar.gz
                with tarfile.open(str(pkg_file), 'r|gz') as tar_file:
                    tar_file.extractall(str(tdir))
            elif pkg_file.suffix == '.zip':
                # TODO: test
                with ZipFile(str(pkg_file), 'r') as zip_file:
                    zip_file.extractall(str(tdir))
            else:
                raise NotImplementedError('File format not supported: {}'.format(pkg_file.name))

            extracted_node_dir = tdir / os.listdir(str(tdir))[0]

            _rmtree(str(self.node_dir))
            shutil.move(str(extracted_node_dir), str(self.node_dir))

    @property
    def installed(self):
        return self.node_dir.exists()


class VersionType(click.ParamType):
    name = 'version'

    def convert(self, value, param, ctx):
        return parse_version(value)


def parse_version(ver_str, prefix=r'^', suffix=r'$'):
    pattern = prefix + r'v?(?P<major>\d+)(\.(?P<minor>\d+))?(\.(?P<build>\d+))?' + suffix
    m = re.match(pattern, ver_str)

    if not m:
        raise ValueError('Must match {}'.format(pattern))

    opt_int = lambda s: None if s is None else int(s)
    return int(m.group('major')), opt_int(m.group('minor')), opt_int(m.group('build'))


def info(msg):
    click.echo(str(msg))


def error(msg):
    click.echo('ERROR: {}'.format(msg), err=True)


@contextmanager
def _temp_dir():
    dirname = tempfile.mkdtemp()
    try:
        yield Path(dirname)
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


def main(args):
    cmd_main(args, standalone=False)


# TODO: merge into install(), usage: 'damn install -l'?
# FIXME: doesn't list all versions
def list_packages(args):
    cmd_list(args, standalone=False)


def install(args):
    cmd_install(args, standalone=False)


def uninstall(args):
    cmd_uninstall(args, standalone=False)


@click.group()
@click.help_option('-h', '--help')
def cmd_main():
    pass


@cmd_main.command('list')
@click.help_option('-h', '--help')
@click.argument('version',
                 metavar='VERSION',
                 required=False,
                 type=VersionType())
@click.option('-p', 'platf',
              help='Platform (e.g. darwin, linux, win)')
@click.option('-a', 'arch',
              metavar='ARCH',
              help='Architecture (e.g. arm64, x64, x86)')
@click.option('-f', 'fmt',
              metavar='FMT',
              help='File format (e.g. tar.gz, zip)')
@click.option('--detect/--no-detect',
              default=True,
              help='Detect platf, arch and fmt, default on')
def cmd_list(version, platf, arch, fmt, detect):
    '''
    List Node packages

    VERSION can be full (e.g. 8.0.0) or partial (e.g. 7.10, v6)
    '''
    damn = DamNode()
    det_platf = damn.detect_platf()
    det_arch = damn.detect_arch()
    det_fmt = damn.detect_fmt()

    if detect:
        platf = platf or det_platf
        arch = arch or det_arch
        fmt = fmt or det_fmt

    info('platf: {}'.format(platf))
    info('arch: {}'.format(arch))
    info('fmt: {}'.format(fmt))

    pkgs = list(damn.iter_packages(version, platf, arch, fmt))

    if not pkgs:
        info('No packages found, version too low or too high?')
        return

    all_platfs = set()
    all_archs = set()
    all_fmts = set()

    for pkg_url, platf, arch, fmt in pkgs:
        all_platfs.add(platf)
        all_archs.add(arch)
        all_fmts.add(fmt)
        info(pkg_url)

    lst = lambda s: ', '.join(sorted(s))
    info('all_platfs: {}'.format(lst(all_platfs)))
    info('all_archs: {}'.format(lst(all_archs)))
    info('all_fmts: {}'.format(lst(all_fmts)))


@cmd_main.command('install')
@click.help_option('-h', '--help')
@click.argument('version',
                 metavar='VERSION',
                 required=False,
                 type=VersionType())
def cmd_install(version):
    '''
    Install Node

    VERSION can be full (e.g. 8.0.0) or partial (e.g. 7.10, v6), latest
    version will be installed if it's partial.
    '''
    damn = DamNode()

    if damn.installed:
        error("Node is already installed, you uninstall it by running 'damn uninstall'")
        raise SystemExit(1)

    platf, arch, fmt = damn.detect_platf_arch_fmt()
    pkgs = list(damn.iter_packages(version, platf, arch, fmt))

    if not pkgs:
        error("Couldn not find suitable package install, run 'damn list' to find out why")
        raise SystemExit(1)

    pkg_url = pkgs[0][0]

    with damn.download_package(pkg_url) as pkg_file:
        damn.install_package(pkg_file)

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
    node_dir = str(damn.node_dir)

    if not yes:
        click.confirm('This will remove {!r}, are you sure?'.format(node_dir, abort=True))

    _rmtree(node_dir)
    click.echo('{!r} removed'.format(node_dir))


def nrun(args, standalone=False, env=None):
    # TODO: refactor and handle exception
    damn = DamNode()

    if not damn.installed:
        error("Node is not yet installed, run 'damn install <version>' to install it")
        raise SystemExit(1)

    bin_dir = damn.node_dir / 'bin'

    if not args:
        for x in os.listdir(str(bin_dir)):
            info(x)
        raise SystemExit(1)

    prog = bin_dir / args[0]
    cmd = [str(prog)] + args[1:]

    try:
        subprocess.check_call(cmd, env=env)
    except subprocess.CalledProcessError as e:
        if standalone:
            raise SystemExit(e.returncode)
        else:
            raise

    if standalone:
        raise SystemExit


def node(args, standalone=False):
    damn = DamNode()
    # TODO: should have nrun -g option instead of inserting NODE_PATH here
    env = {
        'NODE_PATH': str(damn.node_dir / 'lib/node_modules')
    }
    nrun(['node'] + args, standalone=standalone, env=env)


def npm(args, standalone=False):
    nrun(['npm'] + args, standalone=standalone)


def cmd_nrun():
    nrun(sys.argv[1:], standalone=True)


def cmd_node():
    node(sys.argv[1:], standalone=True)


def cmd_npm():
    npm(sys.argv[1:], standalone=True)


if __name__ == '__main__':
    cmd_main()
