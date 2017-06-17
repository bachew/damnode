# -*- coding: utf-8 -*-
from unittest import TestCase, skip
from damnode2 import Damnode
from os import path as osp


class LinksTest(TestCase):
    def damnode(self):
        d = Damnode()
        d.verbose = True
        return d

    def test_read_links_dir(self):
        d = self.damnode()
        entries = d.read_links(data_dir('index'))
        expected = [
            data_dir('index/v1'),
            data_dir('index/v2.tar.gz'),
        ]
        self.assertEqual(expected, entries)

    def test_read_links_file(self):
        d = self.damnode()
        entries = d.read_links(data_dir('index2/index.html'))
        expected = [
            data_dir('index2/v3.zip'),
            "https://nodejs.org/dist/latest-v4.x/node-v4.8.3.tar.gz",
        ]
        self.assertEqual(expected, entries)

    def test_read_links_url(self):
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

    def test_download_url(self):
        d = self.damnode()
        d.cache_dir = data_dir('cache')

        with d.download('https://nodejs.org/dist/latest-v6.x/node-v6.11.0-headers.tar.xz') as filename:
            self.assertEqual(data_dir('cache/node-v6.11.0-headers.tar.xz'), filename)

    def test_download_url(self):
        d = self.damnode()
        url = 'https://nodejs.org/dist/latest-v6.x/node-v6.11.0-headers.tar.xz'

        with d.download(url) as filename:
            self.assertEqual('node-v6.11.0-headers.tar.xz', osp.basename(filename))

    def test_download_url_cached(self):
        d = self.damnode()
        d.cache_dir = data_dir('cache')
        url = 'https://nodejs.org/dist/latest-v7.x/node-v7.10.0-headers.tar.xz'

        with d.download(url) as filename:
            self.assertEqual(data_dir('cache/node-v7.10.0-headers.tar.xz'), filename)
            mtime = osp.getmtime(filename)

        with d.download(url) as filename:
            self.assertEqual(mtime, osp.getmtime(filename))


def data_dir(*path):
    return osp.abspath(osp.join(osp.dirname(__file__), 'testdata', *path))
