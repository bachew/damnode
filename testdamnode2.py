# -*- coding: utf-8 -*-
import shutil
import tempfile
from contextlib import contextmanager
from unittest import TestCase, skip
from damnode2 import Damnode
from os import path as osp


class LinkTest(TestCase):
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

    def test_read_remote_links(self):
        d = create_damnode()
        entries = d.read_links('https://nodejs.org/dist/latest-v5.x/')
        self.assertTrue('https://nodejs.org/dist/latest-v5.x/node-v5.12.0-linux-arm64.tar.gz' in entries, entries)

    def test_has_package_suffix(self):
        d = create_damnode()
        self.assertTrue(d.has_package_suffix('file.tar.gz'))
        self.assertTrue(d.has_package_suffix('file.zip'))

    def test_read_links_package(self):
        d = create_damnode()
        self.assertEqual(['node-v6.xz'], d.read_links('node-v6.xz'))


class NameTest(TestCase):
    def test_parse_package(self):
        d = Damnode()

        self.assertRaisesRegexp(
            ValueError,
            r"Invalid package name 'node.*', suffix must be one of \[",
            d.parse_package, 'node-v8.1.2-win-x64.superzip')

        self.assertEqual(((8, 1, 2), 'linux', 'x64', 'tar.gz'),
                          d.parse_package('node-v8.1.2-linux-x64.tar.gz'))

        self.assertRaisesRegexp(
            ValueError,
            r"Invalid package name 'foobar.*', it does not match regex \^node-",
            d.parse_package, 'foobar-v8.1.2-darwin-x64.tar.gz')

    def test_parse_version(self):
        d = Damnode()
        self.assertEqual((4, None, None), d.parse_version('v4'))
        self.assertEqual((5, 12, None), d.parse_version('5.12'))
        self.assertEqual((6, 11, 0), d.parse_version('v6.11.0'))
        self.assertRaises(ValueError, d.parse_version, '6.11.0.0')
        self.assertRaises(ValueError, d.parse_version, 'node-v6.11.0')


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
    def test_install_tgz(self):
        download_install('https://nodejs.org/dist/v8.1.2/node-v8.1.2-linux-x64.tar.gz')

    def test_install_zip(self):
        self.download_install('https://nodejs.org/dist/v8.1.2/node-v8.1.2-win-x64.zip')

    def download_install(self, url):
        d = Damnode()
        d.verbose = True
        clean = False  # TODO: remove after testing

        with d.download_package(url) as filename, temp_dir(clean) as prefix:
            d.install_package(filename, prefix)


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
