import unittest
import tempfile
import shutil
import os
from os.path import dirname, join

# XXX these can fail because this module can run without depending on
# these.

import zope.component
import zope.interface
from zope.app.component.hooks import getSiteManager
from zope.publisher.browser import TestRequest

import pmr2.mercurial
from pmr2.mercurial import *
from pmr2.mercurial.interfaces import *
from pmr2.mercurial.adapter import *

from pmr2.app.interfaces import IPMR2GlobalSettings

from pmr2.app.workspace.exceptions import *
from pmr2.app.workspace.interfaces import IWorkspace

from zope.configuration.xmlconfig import xmlconfig
from zope.component.tests import clearZCML

# XXX assumption


class PMR2Storage(object):
    zope.interface.implements(IWorkspace)
    def __init__(self, path):
        self.path = path

class Settings(object):
    zope.interface.implements(IPMR2GlobalSettings)
    def dirCreatedFor(self, obj):
        return obj.path

class AdapterTestCase(unittest.TestCase):

    def setUp(self):
        self.testdir = tempfile.mkdtemp()
        self.repodir = join(self.testdir, 'repodir')
        Sandbox.create(self.repodir, True)

        self.revs = []

        sandbox = Sandbox(self.repodir, ctx='tip')
        self.path = dirname(__file__)
        self.filelist = ['file1', 'file2', 'file3',]
        self.nested_name = 'nested/deep/dir/file'
        self.nested_file = 'This is\n\na deeply nested file\n'
        self.files = [open(join(self.path, i)).read() for i in self.filelist]
        self.msg = 'added some files'
        self.user = 'Tester <test@example.com>'

        sandbox.add_file_content('file1', self.files[0])
        sandbox.add_file_content('file2', self.files[0])
        sandbox.commit('added1', 'user1 <1@example.com>')
        self.revs.append(Storage(self.repodir, ctx='tip').rev)

        sandbox.add_file_content('file1', self.files[1])
        sandbox.commit('added2', 'user2 <2@example.com>')
        self.revs.append(Storage(self.repodir, ctx='tip').rev)

        sandbox.add_file_content('file2', self.files[1])
        sandbox.add_file_content('file3', self.files[0])
        sandbox.commit('added3', 'user3 <3@example.com>')
        self.revs.append(Storage(self.repodir, ctx='tip').rev)

        sandbox.add_file_content(self.nested_name, self.nested_file)
        sandbox.commit('added4', 'user3 <3@example.com>')
        self.revs.append(Storage(self.repodir, ctx='tip').rev)

        self.repo = Storage(self.repodir, ctx='tip')
        self.rev = self.repo.rev

        clearZCML()
        xmlconfig(open(join(pmr2.mercurial.__path__[0], 'configure.zcml')))

        # register custom utility that would have normally been done.
        sm = getSiteManager()
        sm.registerUtility(Settings(), IPMR2GlobalSettings)
        self.settings = getUtility(IPMR2GlobalSettings)

    def tearDown(self):
        shutil.rmtree(self.testdir)

    def test_adapter_base(self):
        o = PMR2Storage(self.repodir)
        a = PMR2StorageAdapter(o)
        self.assertEqual(a._changectx(), self.repo._changectx())

        a = zope.component.queryMultiAdapter((o,), name="PMR2Storage")
        self.assertNotEqual(a, None, 'adapter not registered')
        self.assertEqual(a._changectx(), self.repo._changectx())

        # get latest id.
        a._changectx()
        rev = a.rev
        r = TestRequest(rev=rev)
        a = zope.component.queryMultiAdapter((o, r,), name="PMR2StorageRequest")
        self.assertNotEqual(a, None, 'adapter not registered')
        rev2 = a.structure['node']
        self.assertEqual(rev, rev2, 'hgweb revision and default not the same?')

    def test_adapter_rawfile(self):
        o = PMR2Storage(self.repodir)
        r = TestRequest(rev=self.rev, request_subpath=('file1',))
        a = zope.component.queryMultiAdapter((o, r,), name="PMR2StorageRequest")
        self.assertNotEqual(a, None, 'adapter not registered')
        self.assertEqual(a.structure['node'], self.rev)
        fc = a.rawfile
        self.assertEqual(fc, self.files[1])

    def test_adapter_nested_file(self):
        o = PMR2Storage(self.repodir)
        subpath = self.nested_name.split('/')
        r = TestRequest(rev=self.rev, request_subpath=subpath)
        a = zope.component.queryMultiAdapter((o, r,), name="PMR2StorageRequest")
        fc = a.rawfile
        self.assertEqual(fc, self.nested_file)

    def test_adapter_nested_structure_file(self):
        o = PMR2Storage(self.repodir)
        subpath = self.nested_name.split('/')
        entry = subpath.pop()
        r = TestRequest(rev=self.rev, request_subpath=subpath)
        a = zope.component.queryMultiAdapter((o, r,), name="PMR2StorageRequest")
        struct = a.structure
        self.assertEqual(struct[''], 'manifest')
        result = struct['fentries']().next()
        self.assertRaises(StopIteration, struct['dentries']().next)
        self.assertEqual(result['basename'], entry)

    def test_adapter_nested_structure_dir(self):
        o = PMR2Storage(self.repodir)
        subpath = self.nested_name.split('/')
        entry = subpath.pop()
        entry = subpath.pop()
        r = TestRequest(rev=self.rev, request_subpath=subpath)
        a = zope.component.queryMultiAdapter((o, r,), name="PMR2StorageRequest")
        struct = a.structure
        result = struct['dentries']().next()
        self.assertEqual(result['basename'], entry)
        self.assertRaises(StopIteration, struct['fentries']().next)

    def test_adapter_fixedrev(self):
        o = PMR2Storage(self.repodir)
        r = self.revs[1]
        a = zope.component.queryMultiAdapter((o, r,), 
                                             name="PMR2StorageFixedRev")
        self.assertNotEqual(a, None, 'adapter not registered')
        rev2 = a.rev
        self.assertEqual(rev2, r, 'hgweb revision and default not the same?')

        manifest = a.raw_manifest().keys()
        manifest.sort()
        self.assertEqual(['file1', 'file2'], manifest,
            'manifest not locked at specified version')
        # can no longer read another context
        self.assertRaises(TypeError, a, '_filectx', r, 'file1', 
            'revision can no longer be specified.')
        f1 = a.file('file2')
        self.assertEqual(f1, self.files[0], 'local revision file not matched')


def test_suite():
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(AdapterTestCase))
    return suite

if __name__ == '__main__':
    unittest.main()
