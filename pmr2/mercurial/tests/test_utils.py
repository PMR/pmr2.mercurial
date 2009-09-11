import unittest
import tempfile
import shutil
import os
from os.path import dirname, join
from pmr2.mercurial import utils, exceptions


class WebdirTestCase(unittest.TestCase):

    def setUp(self):
        self.rootdir = tempfile.mkdtemp()
        self.repodirs = ['test%d' % i for i in xrange(5)]
        for i in self.repodirs:
            os.mkdir(join(self.rootdir, i))
            # testing only up to limitations

        for i in self.repodirs[1:4]:
            os.mkdir(join(self.rootdir, i, utils._rstub))

    def tearDown(self):
        shutil.rmtree(self.rootdir, ignore_errors=True)

    def test_standard(self):
        self.assert_(utils.webdir(self.rootdir), self.repodirs[1:4])

    def test_with_files(self):
        # stick a random file in place
        o = open(join(self.rootdir, 'file'), 'w')
        o.write('')
        o.close()
        self.assert_(utils.webdir(self.rootdir), self.repodirs[1:4])

    def test_no_permission(self):
        # stick an unreadable directory in place
        os.mkdir(join(self.rootdir, 'noperm'), 0)
        self.assert_(utils.webdir(self.rootdir), self.repodirs[1:4])

    def test_match_subrepo(self):
        # we emulate input
        substate = {
            'mod1': (
                'http://models.example.com/mod1',
                '12345',
            ), 
            'mod2': (
                'https://models.example.com/mod2',
                '67890',
            ),
            'nested/mod3': (
                'https://models.example.com/mod3',
                'abcde',
            ),
            'fail': (
                '/tmp/fail',
                'f0123',
            ),
        }

        result = utils.match_subrepo(substate, 'mod1').next()
        self.assertEqual(result[''], '_subrepo')
        self.assertEqual(result['path'], '')
        self.assertEqual(result['location'], 'http://models.example.com/mod1')
        self.assertEqual(result['rev'], '12345')

        result = utils.match_subrepo(substate, 'mod2/component/test').next()
        self.assertEqual(result[''], '_subrepo')
        self.assertEqual(result['path'], 'component/test')
        self.assertEqual(result['location'], 'https://models.example.com/mod2')
        self.assertEqual(result['rev'], '67890')

        result = utils.match_subrepo(substate, 'nested/mod3/file').next()
        self.assertEqual(result[''], '_subrepo')
        self.assertEqual(result['path'], 'file')
        self.assertEqual(result['location'], 'https://models.example.com/mod3')
        self.assertEqual(result['rev'], 'abcde')

        result = utils.match_subrepo(substate, 'nested/mod3file')
        self.assertEqual(result, None)

        result = utils.match_subrepo(substate, 'mod3/component/test')
        self.assertEqual(result, None)

        self.assertRaises(exceptions.SubrepoPathUnsupportedError,
            utils.match_subrepo, substate, 'fail/local/test')

def test_suite():
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(WebdirTestCase))
    return suite

if __name__ == '__main__':
    unittest.main()
