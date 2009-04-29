import unittest
import tempfile
import shutil
import os
from os.path import dirname, join

# XXX these can fail because this module can run without depending on
# these.

import zope.component
import zope.interface
from zope.publisher.browser import TestRequest

import pmr2.mercurial
from pmr2.mercurial import *
from pmr2.mercurial.interfaces import *
from pmr2.mercurial.adapter import *
from pmr2.mercurial.exceptions import *

from zope.configuration.xmlconfig import xmlconfig
from zope.component.tests import clearZCML

# XXX assumption


class AdapterTestCase(unittest.TestCase):

    def setUp(self):
        self.testdir = tempfile.mkdtemp()
        self.repodir = join(self.testdir, 'repodir')
        Sandbox.create(self.repodir, True)

        sandbox = Sandbox(self.repodir, ctx='tip')
        self.path = dirname(__file__)
        self.filelist = ['file1', 'file2', 'file3',]
        self.files = [open(join(self.path, i)).read() for i in self.filelist]
        self.msg = 'added some files'
        self.user = 'Tester <test@example.com>'
        sandbox.add_file_content('file1', self.files[0])
        sandbox.add_file_content('file2', self.files[0])
        sandbox.commit('added1', 'user1 <1@example.com>')
        sandbox.add_file_content('file1', self.files[1])
        sandbox.commit('added2', 'user2 <2@example.com>')
        sandbox.add_file_content('file2', self.files[1])
        sandbox.add_file_content('file3', self.files[0])
        sandbox.commit('added3', 'user3 <3@example.com>')
        self.repo = Storage(self.repodir, ctx='tip')

    def tearDown(self):
        shutil.rmtree(self.testdir)

    def test_adapter(self):
        class PMR2Storage(object):
            zope.interface.implements(IPMR2StorageBase)
            path = self.repodir
            def get_path(self):
                return self.path

        clearZCML()
        xmlconfig(open(join(pmr2.mercurial.__path__[0], 'configure.zcml')))

        o = PMR2Storage()
        self.assertEqual(o.get_path(), self.repodir)
        a = PMR2StorageAdapter(o)
        self.assertEqual(a._changectx(), self.repo._changectx())

        a = zope.component.queryMultiAdapter((o,), name="PMR2Storage")
        self.assertNotEqual(a, None, 'adapter not registered')
        self.assertEqual(a._changectx(), self.repo._changectx())

        rev = a.manifest().next()['node']
        r = TestRequest(rev=rev)
        a = zope.component.queryMultiAdapter((o, r,), name="PMR2StorageRequest")
        self.assertNotEqual(a, None, 'adapter not registered')
        self.assertEqual(a.fileinfo, None)
        rev2 = a.manifest['node']
        self.assertEqual(rev, rev2)

        r = TestRequest(rev=rev, request_subpath=('file1',))
        a = zope.component.queryMultiAdapter((o, r,), name="PMR2StorageRequest")
        self.assertEqual(a.manifest, None)
        self.assertNotEqual(a, None, 'adapter not registered')
        self.assertEqual(a.fileinfo['node'], rev2)
        fc = a.file
        self.assertEqual(fc, self.files[1])


def test_suite():
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(AdapterTestCase))
    return suite

if __name__ == '__main__':
    unittest.main()
