# -*- coding: utf-8 -*-
import shutil
import tempfile
from contextlib import contextmanager
from unittest import TestCase, skip
from damnode2 import Damnode
from os import path as osp


class LinkTest(TestCase):
    def test_read_remote_links(self):
        d = create_damnode()
        entries = d.read_links('https://nodejs.org/dist/latest-v5.x/')
        self.assertTrue('https://nodejs.org/dist/latest-v5.x/node-v5.12.0-linux-arm64.tar.gz' in entries, entries)

    def test_read_dir_links(self):
        d = create_damnode()
        entries = d.read_links(data_dir('local-index'))
        expected = [
            data_dir('local-index/node-v8.1.2-linux-arm64.tar.gz'),
            data_dir('local-index/old.html'),
            data_dir('local-index/v7.10.0'),
        ]
        self.assertEqual(expected, entries)

    def test_read_local_links(self):
        d = create_damnode()
        entries = d.read_links(data_dir('local-index/old.html'))
        expected = [
            data_dir('local-index/v3'),
            "https://nodejs.org/dist/latest-v4.x",
            "https://nodejs.org/dist/latest-v5.x",
            "https://nodejs.org/dist/latest-v6.x",
            data_dir('local-index/v7.10.0'),
        ]
        self.assertEqual(expected, entries)

    def test_read_links_package(self):
        d = create_damnode()
        self.assertEqual(['node-v6.xz'], d.read_links('node-v6.xz'))


class NameTest(TestCase):
    def test_has_package_suffix(self):
        d = Damnode()
        self.assertTrue(d.has_package_suffix('file.tar.gz'))
        self.assertTrue(d.has_package_suffix('file.zip'))

    def test_is_url(self):
        d = Damnode()
        self.assertTrue(d.is_url('http://localhost'))
        self.assertTrue(d.is_url('https://localhost'))
        self.assertTrue(d.is_url('file://localhost'))
        self.assertFalse(d.is_url('~/Download'))

    def test_parse_package_name(self):
        d = Damnode()

        self.assertRaisesRegexp(
            ValueError,
            r"Invalid package name 'node.*', suffix must be one of \[",
            d.parse_package_name, 'node-v8.1.2-win-x64.superzip')

        self.assertEqual(((8, 1, 2), 'linux', 'x64', 'tar.gz'),
                          d.parse_package_name('node-v8.1.2-linux-x64.tar.gz'))

        self.assertRaisesRegexp(
            ValueError,
            r"Invalid package name 'foobar.*', it does not match regex \^node-",
            d.parse_package_name, 'foobar-v8.1.2-darwin-x64.tar.gz')

    def test_parse_version(self):
        d = Damnode()
        self.assertEqual((4, None, None), d.parse_version('v4'))
        self.assertEqual((5, 12, None), d.parse_version('5.12'))
        self.assertEqual((6, 11, 0), d.parse_version('v6.11.0'))
        self.assertRaisesRegexp(
            ValueError,
            r"Invalid version '6.11.0.0', it does not match regex ",
            d.parse_version, '6.11.0.0')
        self.assertRaises(ValueError, d.parse_version, '6.11.0.0')
        self.assertRaises(ValueError, d.parse_version, 'node-v6.11.0')

    def test_get_system(self):
        d = Damnode()
        test = lambda a, b: self.assertEqual(d._get_system(a), b)
        test('AIX', 'aix')
        test('Darwin', 'darwin')
        test('Linux', 'linux')
        test('Solaris', 'sunos')
        test('Windows', 'win')

    def test_get_compatible_arch(self):
        d = Damnode()
        test = lambda m, p, a: self.assertEqual(d._get_compatible_arch(m, p), a)

        # https://en.wikipedia.org/wiki/Uname
        test('armv7l', '', 'armv7l')
        test('armv6l', '', 'armv6l')
        test('i686', '', 'x86')
        test('i686', 'i686', 'x86')
        test('x86_64', '', 'x64')
        test('x86_64', 'x86_64', 'x64')
        test('i686-AT386', '', 'x86')
        test('amd64', '', 'x64')
        test('amd64', 'amd64', 'x64')
        test('x86', 'Intel_x86_Family6_Model28_Stepping10', 'x86')
        test('i686-64', 'x64', 'x64')

        # PowerPC
        # - https://en.wikipedia.org/wiki/Uname
        # - https://github.com/ansible/ansible/pull/2311
        test('ppc', '', 'ppc64')  # no ppc packages
        test('ppc64', 'ppc64', 'ppc64')
        test('ppc64le', 'ppc64le', 'ppc64le')
        test('00C57D4D4C00', 'powerpc', 'ppc64')
        test('Power Macintosh', 'powerpc', 'ppc64')

        # https://stackoverflow.com/questions/31851611/differences-between-arm64-and-aarch64
        test('arm64', '', 'arm64')
        test('aarch64', '', 'arm64')

        # https://en.wikipedia.org/wiki/Linux_on_z_Systems
        test('s390', 's390', 's390x')  # no s390 packages
        test('s390x', 's390x', 's390x')

        # Unsupported
        test('sparc64', 'sparc64', 'sparc64')


class DownloadTest(TestCase):
    def test_download_local_package(self):
        d = create_damnode()

        with d.download_package(data_dir('local-index/node-v8.1.2-linux-arm64.tar.gz')) as filename:
            self.assertEqual(data_dir('cache/node-v8.1.2-linux-arm64.tar.gz'), filename)

    def test_download_remote_package(self):
        d = create_damnode()
        url = 'https://nodejs.org/dist/latest-v6.x/node-v6.11.0-win-x64.zip'

        with d.download_package(url) as filename:
            self.assertEqual(osp.join(d.cache_dir, 'node-v6.11.0-win-x64.zip'), filename)
            mtime = osp.getmtime(filename)

        with d.download_package(url) as filename:
            self.assertEqual(mtime, osp.getmtime(filename))

    def test_download_none_package(self):
        d = create_damnode()
        try:
            with d.download_package('https://nodejs.org/dist/not-node.zip') as filename:
                pass
        except ValueError as e:
            pass
        else:
            self.fail('Exception not raised')

    def test_download_cached_package(self):
        d = create_damnode()
        url = 'https://nodejs.org/dist/latest-v6.x/node-v6.11.0-darwin-x64.tar.gz'
        cached_file = osp.join(d.cache_dir, 'node-v6.11.0-darwin-x64.tar.gz')

        with d.download_package(url) as filename:
            self.assertEqual(cached_file, filename)
            mtime = int(osp.getmtime(filename))  # shutil.copystat() is not perfect

        d.cache_dir = data_dir('cache2')

        if osp.exists(d.cache_dir):
            shutil.rmtree(d.cache_dir)

        with d.download_package(cached_file) as filename:
            self.assertEqual(data_dir('cache2/node-v6.11.0-darwin-x64.tar.gz'), filename)
            self.assertEqual(mtime, int(osp.getmtime(filename)))

    def test_download_package_no_cache(self):
        d = create_damnode()
        d.enable_cache = False
        unused_cache_dir = data_dir('cache3')
        d.cache_dir = unused_cache_dir

        with d.download_package(data_dir('cache/node-v6.11.0-win-x64.zip')) as filename:
            self.assertNotEqual(unused_cache_dir, d.cache_dir)
            self.assertTrue(filename.startswith(d.cache_dir))

        self.assertEqual(unused_cache_dir, d.cache_dir)
        self.assertFalse(osp.exists(unused_cache_dir))


class InstallTest(TestCase):
    def test_install_wrong_system(self):
        with temp_dir() as prefix:
            url = 'https://nodejs.org/dist/latest-v8.x/node-v8.1.2-aix-ppc64.tar.gz'
            self.assertRaisesRegexp(
                ValueError,
                r"Package '.*/node-v8.1.2-aix-ppc64.tar.gz' is for aix-ppc64, not for current .*",
                self.download_install, url, prefix, True)

    def test_install_tgz(self):
        with temp_dir() as prefix:
            url = 'https://nodejs.org/dist/v8.1.2/node-v8.1.2-linux-x64.tar.gz'
            self.download_install(url, prefix)
            self.assertFalse(osp.exists(osp.join(prefix, 'CHANGELOG.md')))
            self.assertFalse(osp.exists(osp.join(prefix, 'LICENSE')))
            self.assertFalse(osp.exists(osp.join(prefix, 'README.md')))
            self.assertTrue(osp.isfile(osp.join(prefix, 'bin/node')))

    def test_install_win_zip(self):
        with temp_dir() as prefix:
            url = 'https://nodejs.org/dist/v8.1.2/node-v8.1.2-win-x64.zip'
            self.download_install(url, prefix)
            self.assertFalse(osp.exists(osp.join(prefix, 'README.md')))
            self.assertTrue(osp.isdir(osp.join(prefix, 'node_modules')))
            self.assertTrue(osp.isfile(osp.join(prefix, 'node.exe')))

    def download_install(self, url, prefix, check_sys_arch=False):
        d = Damnode()
        d.prefix = prefix
        # d.verbose = True
        d.check_sys_arch = check_sys_arch
        d.download_install_package(url)

    # TODO: test uninstall


def data_dir(*path):
    return osp.abspath(osp.join(osp.dirname(__file__), 'testdata', *path))


def create_damnode():
    d = Damnode()
    d.cache_dir = data_dir('cache')
    d.verbose = True
    return d


@contextmanager
def temp_dir(clean=True):
    dirname = tempfile.mkdtemp()
    try:
        yield dirname
    finally:
        if clean:
            shutil.rmtree(dirname)
