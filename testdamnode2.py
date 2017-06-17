# -*- coding: utf-8 -*-
from unittest import TestCase, skip
from damnode2 import Damnode
from os import path as osp


class ListingTest(TestCase):
    def test_list_index_dir(self):
        d = Damnode()
        entries = d.list_index(data_dir('index'))
        expected = [
            data_dir('index/v1'),
            data_dir('index/v2.tar.gz'),
        ]
        self.assertEqual(expected, entries)

    def test_list_index_file(self):
        d = Damnode()
        entries = d.list_index(data_dir('index2/index.html'))
        expected = [
            data_dir('index2/v3.zip'),
            "https://nodejs.org/dist/latest-v4.x/node-v4.8.3.tar.gz",
        ]
        self.assertEqual(expected, entries)

    # @skip('Temporary')
    def test_list_index_url(self):
        d = Damnode()
        entries = d.list_index('https://nodejs.org/dist/latest-v5.x/')
        self.assertTrue('https://nodejs.org/dist/latest-v5.x/node-v5.12.0-linux-arm64.tar.gz' in entries, entries)

    def test_list_package_as_index(self):
        d = Damnode()
        self.assertRaisesRegexp(
            ValueError,
            r"'v4\.tar\.gz' is a package, not an index",
            d.list_index, 'v4.tar.gz')
        self.assertRaisesRegexp(
            ValueError,
            r"'v5\.xz' is a package, not an index",
            d.list_index, 'v5.xz')


def data_dir(*path):
    return osp.abspath(osp.join(osp.dirname(__file__), 'testdata', *path))
