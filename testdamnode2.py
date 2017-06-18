# -*- coding: utf-8 -*-
import shutil
from unittest import TestCase, skip
from damnode2 import Damnode
from os import path as osp


class NameTest(TestCase):
    def test_parse_package(self):
        d = Damnode()
        self.assertEqual(((8, 1, 2), 'darwin', 'x64', 'tar.gz'),
                          d.parse_package('node-v8.1.2-darwin-x64.tar.gz'))
        self.assertRaises(ValueError, d.parse_package, 'foobar-v8.1.2-darwin-x64.tar.gz')
        self.assertRaises(ValueError, d.parse_package, 'node-v8.1.2-darwin-x64')

    def test_parse_version(self):
        d = Damnode()
        self.assertEqual((4, None, None), d.parse_version('v4'))
        self.assertEqual((5, 12, None), d.parse_version('5.12'))
        self.assertEqual((6, 11, 0), d.parse_version('v6.11.0'))
        self.assertRaises(ValueError, d.parse_version, '6.11.0.0')
        self.assertRaises(ValueError, d.parse_version, 'node-v6.11.0')

    # TODO: use parse_package in is_package, update IoTest


class IoTest(TestCase):
    def damnode(self):
        d = Damnode()
        d.verbose = True
        d.cache_dir = data_dir('cache')
        return d

    def test_read_links_dir(self):
        d = self.damnode()
        entries = d.read_links(data_dir('index'))
        expected = [
            data_dir('index/v1'),
            data_dir('index/v2.tar.gz'),
        ]
        self.assertEqual(expected, entries)

    def test_read_local_links(self):
        d = self.damnode()
        entries = d.read_links(data_dir('index2/index.html'))
        expected = [
            data_dir('index2/v3.zip'),
            "https://nodejs.org/dist/latest-v4.x/node-v4.8.3.tar.gz",
        ]
        self.assertEqual(expected, entries)

    def test_read_remote_links(self):
        d = self.damnode()
        entries = d.read_links('https://nodejs.org/dist/latest-v5.x/')
        self.assertTrue('https://nodejs.org/dist/latest-v5.x/node-v5.12.0-linux-arm64.tar.gz' in entries, entries)

    def test_is_package(self):
        d = self.damnode()
        self.assertTrue(d.is_package('v4.tar.gz'))
        self.assertTrue(d.is_package('v5.zip'))

    def test_read_links_package(self):
        d = self.damnode()
        self.assertRaisesRegexp(
            ValueError,
            r"'v6\.xz' is a package, does not have links",
            d.read_links, 'v6.xz')

    def test_download_local(self):
        d = self.damnode()

        with d.download(data_dir('index/v2.tar.gz')) as filename:
            self.assertEqual(data_dir('index/v2.tar.gz'), filename)

    def test_download_index(self):
        d = self.damnode()
        try:
            with d.download('https://nodejs.org/dist/') as filename:
                pass
        except ValueError as e:
            self.assertEqual("'https://nodejs.org/dist/' is not a package and cannot be downloaded", str(e))
        else:
            self.fail('Exception not raised')

    def test_download_local(self):
        d = self.damnode()
        url = 'https://nodejs.org/dist/latest-v6.x/node-v6.11.0-headers.tar.xz'
        cached_file = osp.join(d.cache_dir, 'node-v6.11.0-headers.tar.xz')

        with d.download(url) as filename:
            self.assertEqual(cached_file, filename)
            mtime = int(osp.getmtime(filename))  # shutil.copystat() is not perfect

        d.cache_dir = data_dir('cache2')
        shutil.rmtree(d.cache_dir)

        with d.download(cached_file) as filename:
            self.assertEqual(data_dir('cache2/node-v6.11.0-headers.tar.xz'), filename)
            self.assertEqual(mtime, int(osp.getmtime(filename)))

    def test_download_remote(self):
        d = self.damnode()
        url = 'https://nodejs.org/dist/latest-v6.x/node-v6.11.0-headers.tar.xz'

        with d.download(url) as filename:
            self.assertEqual(osp.join(d.cache_dir, 'node-v6.11.0-headers.tar.xz'), filename)
            mtime = osp.getmtime(filename)

        with d.download(url) as filename:
            self.assertEqual(mtime, osp.getmtime(filename))

    def test_download_no_cache(self):
        d = self.damnode()
        d.cache = False
        d.cache_dir = 'does-not-matter'

        with d.download(data_dir('cache/node-v6.11.0-headers.tar.xz')) as filename:
            self.assertNotEqual('does-not-matter', d.cache_dir)
            self.assertTrue(filename.startswith(d.cache_dir))

        self.assertEqual('does-not-matter', d.cache_dir)


def data_dir(*path):
    return osp.abspath(osp.join(osp.dirname(__file__), 'testdata', *path))
