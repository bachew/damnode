# -*- coding: utf-8 -*-
import appdirs
import click
import errno
import functools
import os
import platform
import re
import requests
import shutil
import sys
import tarfile
import tempfile
import zipfile
from contextlib import contextmanager
from fnmatch import fnmatch
from os import path as osp
from six.moves.html_parser import HTMLParser
from six.moves.urllib import parse as urlparse


def cached_property(method):
    @functools.wraps(method)
    def wrapped(self):
        key = '_' + method.__name__

        if not hasattr(self, key):
            setattr(self, key, method(self))

        return getattr(self, key)

    return property(wrapped)


class Damnode(object):
    def _get_default_cache_dir():
        app_name = osp.splitext(osp.basename(__file__))[0]
        app_author = app_name  # makes no sense to use my name
        return appdirs.user_cache_dir(app_name, app_name)

    default_cache_dir = _get_default_cache_dir()
    default_index = 'https://nodejs.org/dist/'
    default_prefix = sys.prefix

    _package_re = re.compile(r'^node-(?P<version>[^-]+)-(?P<platform>[^-]+)-(?P<arch>[^\.]+)\.(?P<format>.+)$')
    _version_re = re.compile(r'^v?(?P<major>\d+)(\.(?P<minor>\d+))?(\.(?P<build>\d+))?$')

    def __init__(self):
        self.verbose = False
        self.enable_cache = True
        self.cache_dir = self.default_cache_dir
        self.download_chunk_size = 10 * 1024
        self.package_suffixes = ['.gz', '.msi', '.pkg', '.xz', '.zip']
        self.url_prefixes = ['http://', 'https://', 'file://']
        self.prefix = self.default_prefix
        self.check_sys_arch = False
        self._indices = [self.default_index]

    def info(self, msg):
        click.echo(str(msg))

    def debug(self, msg):
        if self.verbose:
            self.info('DEBUG: {}'.format(msg))

    def install(self, hint):
        if hint and self.has_package_suffix(hint):
            self.download_install_package(hint)
            return

        indices = list(self._indices)

        if hint:
            if self.is_url(hint):
                indices = [hint]  # TODO: or just fail?
            else:
                version = self.parse_version(hint)
        else:
            version = None

        self.debug('indices = {!r}'.format(indices))
        self.debug('version = {!r}'.format(version))
        self.debug('system = {!r}'.format(self.system))
        self.debug('arch = {!r}'.format(self.architecture))
        self.debug('fmt = {!r}'.format(self.archive_format))

        for index in indices:
            link = self.find_package(index, version)

            if link:
                self.download_install_package(link)
                return

    def uninstall(self):
        self.info('TODO')

    def append_index(self, index):
        self._indices.append(index)

    def prepend_index(self, index):
        self._indices.insert(0, index)

    def find_package(self, index, version):
        links = self.read_links(index)
        verlinks = []

        for link in links:
            ver_str = osp.basename(osp.abspath(link))  # without end /
            try:
                ver = self.parse_version(ver_str)
            except ValueError:
                pass
            else:
                verlinks.append((ver, link))

        verlinks = reversed(verlinks)
        match = lambda a, b: a is None or a == b
        version_link = None

        for ver, link in verlinks:
            if version is None or match(version[0], ver[0]) and match(version[1], ver[1]) and match(version[2], ver[2]):
                version_link = link
                break

        if not version_link:
            return

        package_links = self.read_links(version_link)

        for link in package_links:
            try:
                ver, system, arch, fmt = self.parse_package_name(osp.basename(link))
            except ValueError:
                pass
            else:
                if (version is None or ver == version) and system == self.system and arch == self.architecture and self.archive_format == fmt:
                    return link

        return None


    def read_links(self, link):
        self.info('Reading links from {!r}'.format(link))

        if self.has_package_suffix(link):
            return [link]

        read_html = lambda h: HtmlLinksParser(link, h).links

        if self.is_url(link):
            resp = requests.get(link)
            return read_html(resp.text)

        try:
            entries = os.listdir(link)
        except EnvironmentError as e:
            if e.errno in (errno.ENOENT, errno.ENOTDIR):
                pass
            else:
                raise
        else:
            return sorted([osp.join(link, e) for e in entries])  # sort from file system

        try:
            with open(link, 'r') as f:
                html = f.read()
        except EnvironmentError as e:
            if e.errno  == errno.ENOENT:
                pass
            else:
                raise
        else:
            return read_html(html)

    def download_install_package(self, link):
        with self.download_package(link) as filename:
            self.install_package(filename)

    @contextmanager
    def download_package(self, link):
        name = osp.basename(link)
        self.parse_package_name(name)

        with self._ensure_cache_dir():
            cached_file = osp.join(self.cache_dir, name)

            if osp.isfile(cached_file):
                self.info('Using cached {!r}'.format(cached_file))
                yield cached_file
            elif self.is_url(link):
                temp_fd, temp_file = tempfile.mkstemp(prefix='{}.download-'.format(name),
                                                      dir=self.cache_dir)
                try:
                    self.info('Downloading {!r}'.format(link))
                    self.debug('Downloading to temp file {!r}'.format(temp_file))

                    with open(temp_file, 'wb') as f:
                        resp = requests.get(link, stream=True)

                        for chunk in self._iter_resp_chunks(resp):
                            f.write(chunk)

                    self.debug('Rename {!r} to {!r}'.format(temp_file, cached_file))
                except:
                    os.remove(temp_file)
                    raise
                else:
                    os.rename(temp_file, cached_file)

                yield cached_file
            else:
                self.info('Copying {!r}'.format(link))
                shutil.copyfile(link, cached_file)
                shutil.copystat(link, cached_file)
                yield cached_file

    def install_package(self, package_file):
        self.info('Installing {!r}'.format(package_file))

        version, platf, arch, fmt = self.parse_package_name(osp.basename(package_file))

        if self.check_sys_arch:
            if platf != self.system or arch != self.architecture:
                raise ValueError('Package {!r} is for {}-{}, not for current {}-{}'.format(
                    package_file, platf, arch, self.system, self.architecture))

        allowed_root_files = []

        if platf == 'win':
            allowed_root_files.extend(['node*', 'npm*', '*.exe', '*.cmd', '*.bat'])

        def is_root_file_allowed(filename):
            for pattern in allowed_root_files:
                if fnmatch(filename, pattern):
                    return True
            return False

        for out_file, extract in self.iter_package_members(package_file):
            if not osp.dirname(out_file) and not is_root_file_allowed(out_file):
                self.debug('Skip {!r}'.format(out_file))
            else:
                self.debug('Install {!r}'.format(osp.join(self.prefix, out_file)))
                extract(self.prefix)

    def iter_package_members(self, package_file):
        tgz_suffix = '.tar.gz'
        zip_suffix = '.zip'

        def iter_tgz():
            with tarfile.open(package_file) as ar:
                base_dir = osp.basename(package_file[:-len(tgz_suffix)])

                for member in ar:
                    if not member.isdir():
                        member.name = osp.relpath(member.name, base_dir)
                        yield member.name, lambda p: ar.extract(member, p)

        def iter_zip():
            with zipfile.ZipFile(package_file) as ar:
                base_dir = osp.basename(package_file[:-len(zip_suffix)])

                for info in ar.infolist():
                    if not info.filename.endswith('/'):
                        info.filename = osp.relpath(info.filename, base_dir)
                        yield info.filename, lambda p: ar.extract(info, p)

        mapping = [
            (tgz_suffix, iter_tgz),
            (zip_suffix, iter_zip),
        ]

        for suffix, func in mapping:
            if package_file.endswith(suffix):
                return func()

        return ValueError

    @contextmanager
    def _ensure_cache_dir(self):
        if self.enable_cache:
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
        chunk_size = self.download_chunk_size
        try:
            content_length = int(resp.headers.get('content-length', ''))
        except ValueError:
            # No Content-Length, no progress
            for chunk in resp.iter_content(chunk_size=chunk_size):
                yield chunk
        else:
            # Got Content-Length, show progress bar
            with click.progressbar(length=content_length) as progress:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    yield chunk
                    progress.update(chunk_size)

    def is_url(self, link):
        for prefix in self.url_prefixes:
            if link.startswith(prefix):
                return True

        return False

    def has_package_suffix(self, link):
        for suffix in self.package_suffixes:
            if link.endswith(suffix):
                return True

        return False

    def parse_package_name(self, name):
        if not self.has_package_suffix(name):
            raise ValueError('Invalid package name {!r}, suffix must be one of {!r}'.format(
                name, self.package_suffixes))

        m = self._package_re.match(name)

        if not m:
            raise ValueError('Invalid package name {!r}, it does not match regex {}'.format(
                name, self._package_re.pattern))

        version = self.parse_version(m.group('version'))
        platf = m.group('platform')  # TODO: -> system
        arch = m.group('arch')
        fmt = m.group('format')
        return version, platf, arch, fmt

    def parse_version(self, name):
        m = self._version_re.match(name)

        if not m:
            raise ValueError('Invalid version {!r}, it does not match regex {}'.format(
                name, self._version_re.pattern))

        opt_int = lambda i: None if i is None else int(i)
        return int(m.group('major')), opt_int(m.group('minor')), opt_int(m.group('build'))

    @cached_property
    def system(self):
        return self._get_system(platform.system())

    def _get_system(self, value):
        value = value.lower()

        dct = {
            'solaris': 'sunos',
            'windows': 'win',
        }
        return dct.get(value, value)

    @cached_property
    def archive_format(self):
        return 'zip' if self.system == 'win' else 'tar.gz'

    @cached_property
    def architecture(self):
        return self._get_compatible_arch(platform.machine(), platform.processor())

    def _get_compatible_arch(self, machine, processor):
        patterns = [
            (r'^i686-64$', 'x64'),
            (r'^i686', 'x86'),
            (r'^x86_64$', 'x64'),
            (r'^amd64$', 'x64'),
            (r'^ppc$', 'ppc64'),
            (r'^powerpc$', 'ppc64'),
            (r'^aarch64$', 'arm64'),
            (r'^s390', 's390x'),
        ]
        simpify = lambda v: '' if v is None else v.lower()
        machine = simpify(machine)
        processor = simpify(processor)

        for patt, arch in patterns:
            pattc = re.compile(patt)

            if pattc.match(machine) or pattc.match(processor):
                return arch

        return machine


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
