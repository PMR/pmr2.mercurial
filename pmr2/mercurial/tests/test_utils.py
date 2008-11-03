import unittest
import tempfile
import shutil
import os
from os.path import dirname, join
from pmr2.mercurial import utils


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


def test_suite():
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(WebdirTestCase))
    return suite

if __name__ == '__main__':
    unittest.main()
