# -*- coding: utf-8 -*-
from unittest import TestCase
from damnode import DamNode, parse_version


class Test(TestCase):
    def setUp(self):
        self.damn = DamNode()

    def test_parse_version(self):
        def test(expected, ver_str, **kwargs):
            actual = parse_version(ver_str, **kwargs)
            self.assertEqual(expected, actual)

        test((4, 0, 0), '4.0.0')
        test((5, 0, None), '5.0')
        test((6, None, None), '6')
        test((7, 0, None), 'v7.0')
        test((8, None, None), ' 8 ', prefix=r'\s*', suffix=r'\s*')

    def test_parse_version_value_error(self):
        def test(message, ver_str, **kwargs):
            self.assertRaisesRegexp(
                ValueError,
                message,
                parse_version, ver_str, **kwargs)

        test(r'^Must match', 'node-v4')

    def test_map(self):
        mapping = [
            (r'^x86[^\d]64$', 'x64'),
            (r'^amd64$', 'x64'),
            (r'^x86[^\d]?', 'x86'),
        ]
        m = lambda v: self.damn.map(mapping, v)
        self.assertEqual('x64', m('x86_64'))
        self.assertEqual('x64', m('amd64'))
        self.assertEqual('x86', m('x86_32'))
        self.assertEqual('x86', m('x86'))
        self.assertEqual('x86', m('x86_128'))
        self.assertEqual('x88', m('x88'))
