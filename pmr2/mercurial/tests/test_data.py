import tarfile
import unittest
import tempfile
import shutil
import os
from os.path import basename, join, splitext

# XXX these can fail because this module can run without depending on
# these.

import zope.component
import zope.interface
from zope.app.component.hooks import getSiteManager
from zope.publisher.browser import TestRequest
from zope.configuration.xmlconfig import xmlconfig
from zope.component.tests import clearZCML

import Acquisition

from pmr2.app.workspace.exceptions import *
from pmr2.app.workspace.interfaces import IWorkspace

import pmr2.mercurial
from pmr2.mercurial import *
from pmr2.mercurial.interfaces import *
from pmr2.mercurial.adapter import *

from pmr2.mercurial.tests import util

# Lightweight helper objects

class Location(object):
    def __init__(self, name):
        self.__name__ = name

class Folder(Location, Acquisition.Implicit):
    def __init__(self, id_):
        super(Folder, self).__init__(id_)
        self.d = {}
    def __of__(self, other):
        acquired = super(Folder, self).__of__(other)
        other.__setitem__(self.__name__, acquired)
        return acquired
    def __setitem__(self, key, value):
        self.d[key] = value
    def __getitem__(self, key):
        return self.d[key]

class PMR2Storage(Folder):
    zope.interface.implements(IWorkspace)
    def __init__(self, path):
        Folder.__init__(self, basename(path))
        self.path = path
    def absolute_url(self):
        baseuri = 'http://models.example.com/w/'
        return baseuri + basename(self.path)

class Settings(object):
    zope.interface.implements(IPMR2GlobalSettings)
    def dirCreatedFor(self, obj):
        return obj.path


class DataTestCase(unittest.TestCase):

    def setUp(self):

        # setup/configure paths
        self.archive_revs = util.ARCHIVE_REVS
        self.archive_name = util.ARCHIVE_NAME
        self.root_name = splitext(self.archive_name)[0]
        self.tempdir = tempfile.mkdtemp()

        self.import1_name = 'import1'
        self.import1_path = join(self.tempdir, self.import1_name)

        self.import2_name = 'import2'
        self.import2_path = join(self.tempdir, self.import2_name)

        # The structure of the repo follows
        # pmr2hgtest is the main archive
        # - first rev it imports nothing
        # - second rev it has import1 as subrepo
        # - third rev it adds import2 as subrepo
        # - forth rev it references updated import 1 and 2
        # import1 first rev imports nthing
        # - rev2 it imports 2

        util.extract_archive(self.tempdir)

        # build test environ.
        self.repodir = join(self.tempdir, self.root_name)
        clearZCML()
        xmlconfig(open(join(pmr2.mercurial.__path__[0], 'configure.zcml')))

        # register custom utility that would have normally been done.
        sm = getSiteManager()
        sm.registerUtility(Settings(), IPMR2GlobalSettings)
        self.settings = getUtility(IPMR2GlobalSettings)

        # create some sort of common container
        self.w = Folder('w')
        # creating the base objects and plug them into our "folder"
        self.pmr2hgtest = PMR2Storage(self.repodir).__of__(self.w)
        self.import1 = PMR2Storage(self.import1_path).__of__(self.w)
        self.import2 = PMR2Storage(self.import2_path).__of__(self.w)

    def tearDown(self):
        shutil.rmtree(self.tempdir)

    def test_000_basic(self):
        o = self.pmr2hgtest
        r = TestRequest(rev=self.archive_revs[0], request_subpath=('file1',))
        a = zope.component.queryMultiAdapter((o, r,), name="PMR2StorageRequest")
        self.assertEqual(self.archive_revs[0], a.rev)
        files = a.raw_manifest().keys()
        files.sort()
        self.assertEqual(files, ['README', 'file1',], 
            'internal changeset context have been changed?')

    def archiver_tester(self, answers, id_, subrepo=True):
        """\
        The core archive tester.
        """

        o = self.pmr2hgtest
        r = TestRequest(rev=self.archive_revs[id_], request_subpath=('gz',))
        a = zope.component.queryMultiAdapter((o, r,), name="PMR2StorageRequest")
        out = a.archive(subrepo=subrepo)
        out.seek(0)
        testtf = tarfile.open('test', 'r:gz', out)
        names = [i.name for i in testtf.getmembers()]
        for check in answers:
            self.assert_(check in names, 
                "'%s' not found in archive." % (check))
            if answers[check] is not None:
                self.assertEqual(testtf.extractfile(check).read(), 
                    answers[check], 'extracted data not as expected.')
        complete = answers.keys()
        complete.sort()
        names.sort()
        self.assertEqual(names, complete, 'list of files incomplete')
        # XXX can't test response headers because test response provides
        # limited features

    def test_100_archive(self):
        """\
        Standard archive test.
        """

        answers = {
            'pmr2hgtest-eb2615b6ebf9/.hg_archival.txt':
                None,
            'pmr2hgtest-eb2615b6ebf9/README':
                'This is a simple test repository for PMR2.\n',
            'pmr2hgtest-eb2615b6ebf9/file1':
                'This is file1, initial commit.\n',
        }
        self.archiver_tester(answers, 0)

    def test_101_archive(self):
        """\
        Include import archive test.
        """

        answers = {
            'pmr2hgtest-c7888f70e7ee/.hg_archival.txt':
                None,
            'pmr2hgtest-c7888f70e7ee/.hgsub':
                'ext/import1 = http://models.example.com/w/import1\n',
            'pmr2hgtest-c7888f70e7ee/.hgsubstate':
                'ce679be0c07e30e81f93cc308ccdaab97b4da313 ext/import1\n',
            'pmr2hgtest-c7888f70e7ee/README':
                'This is a simple test repository for PMR2.\n',
            'pmr2hgtest-c7888f70e7ee/file1':
                'This is file1, initial commit.\n',
            'pmr2hgtest-c7888f70e7ee/ext/import1/.hg_archival.txt':
                None,
            'pmr2hgtest-c7888f70e7ee/ext/import1/README':
                'this is import1\n',
        }
        self.archiver_tester(answers, 1)

    def test_102_archive(self):
        """\
        Include more import archive test and changes.
        """

        answers = {
            'pmr2hgtest-d52a32a5fa62/.hg_archival.txt':
                None,
            'pmr2hgtest-d52a32a5fa62/.hgsub':
                'ext/import1 = http://models.example.com/w/import1\n',
            'pmr2hgtest-d52a32a5fa62/.hgsubstate':
                '3952b4ff62a6062b830113430d300171ca402d8b ext/import1\n',
            'pmr2hgtest-d52a32a5fa62/README':
                'This is a simple test repository for PMR2.\n',
            'pmr2hgtest-d52a32a5fa62/file1':
                'This is file1.\nYes there are changes.\n',
            'pmr2hgtest-d52a32a5fa62/file2':
                'This is file2\n',
            'pmr2hgtest-d52a32a5fa62/ext/import1/.hg_archival.txt':
                None,
            'pmr2hgtest-d52a32a5fa62/ext/import1/README':
                'this is import1\n',
            'pmr2hgtest-d52a32a5fa62/ext/import1/if1':
                'if1\n',
        }
        self.archiver_tester(answers, 2)

    def test_103_archive(self):
        """\
        main imports import2
        """

        answers = {
            'pmr2hgtest-d2759ae2454c/.hg_archival.txt':
                None,
            'pmr2hgtest-d2759ae2454c/.hgsub':
                'ext/import1 = http://models.example.com/w/import1\n'
                'ext/import2 = http://models.example.com/w/import2\n',
            'pmr2hgtest-d2759ae2454c/.hgsubstate':
                '3952b4ff62a6062b830113430d300171ca402d8b ext/import1\n'
                'a413e4d7eb3846209aa8df44addf625093aac231 ext/import2\n',
            'pmr2hgtest-d2759ae2454c/README':
                'This is a simple test repository for PMR2.\n',
            'pmr2hgtest-d2759ae2454c/file1':
                'This is file1.\n'
                'Yes there are changes.\n',
            'pmr2hgtest-d2759ae2454c/file2':
                'This is file2\n',
            'pmr2hgtest-d2759ae2454c/ext/import1/.hg_archival.txt':
                None,
            'pmr2hgtest-d2759ae2454c/ext/import1/README':
                'this is import1\n',
            'pmr2hgtest-d2759ae2454c/ext/import1/if1':
                'if1\n',
            'pmr2hgtest-d2759ae2454c/ext/import2/.hg_archival.txt':
                None,
            'pmr2hgtest-d2759ae2454c/ext/import2/README':
                'this is import2\n',
        }
        self.archiver_tester(answers, 3)

    def test_104_archive(self):
        """\
        Now import1 imports import2 also
        """

        answers = {
            'pmr2hgtest-0ab9d678be93/.hg_archival.txt':
                None,
            'pmr2hgtest-0ab9d678be93/.hgsub':
                'ext/import1 = http://models.example.com/w/import1\n'
                'ext/import2 = http://models.example.com/w/import2\n',
            'pmr2hgtest-0ab9d678be93/.hgsubstate':
                '4df76eccfee8a0d27844b5c069bc399bb0e4e043 ext/import1\n'
                'a413e4d7eb3846209aa8df44addf625093aac231 ext/import2\n',
            'pmr2hgtest-0ab9d678be93/README':
                'This is a simple test repository for PMR2.\n',
            'pmr2hgtest-0ab9d678be93/file1':
                'This is file1.\n'
                'Yes there are changes.\n',
            'pmr2hgtest-0ab9d678be93/file2':
                'This is file2\n',
            'pmr2hgtest-0ab9d678be93/ext/import1/.hg_archival.txt':
                None,
            'pmr2hgtest-0ab9d678be93/ext/import1/.hgsub':
                'import2 = http://models.example.com/w/import2\n',
            'pmr2hgtest-0ab9d678be93/ext/import1/.hgsubstate':
                'a413e4d7eb3846209aa8df44addf625093aac231 import2\n',
            'pmr2hgtest-0ab9d678be93/ext/import1/README':
                'this is import1\n',
            'pmr2hgtest-0ab9d678be93/ext/import1/if1':
                'if1\n',
            'pmr2hgtest-0ab9d678be93/ext/import1/import2/.hg_archival.txt':
                None,
            'pmr2hgtest-0ab9d678be93/ext/import1/import2/README':
                'this is import2\n',
            'pmr2hgtest-0ab9d678be93/ext/import2/.hg_archival.txt':
                None,
            'pmr2hgtest-0ab9d678be93/ext/import2/README':
                'this is import2\n',
        }
        self.archiver_tester(answers, 4)

    def test_105_archive(self):
        """\
        Now this import of import2 is bumpped up a revision but import1 
        remain the same
        """

        answers = {
            'pmr2hgtest-c9226c3a0855/.hg_archival.txt':
                None,
            'pmr2hgtest-c9226c3a0855/.hgsub':
                'ext/import1 = http://models.example.com/w/import1\n'
                'ext/import2 = http://models.example.com/w/import2\n',
            'pmr2hgtest-c9226c3a0855/.hgsubstate':
                '4df76eccfee8a0d27844b5c069bc399bb0e4e043 ext/import1\n'
                '60baac932b072c20fc7004c158ad2b1f5c80de14 ext/import2\n',
            'pmr2hgtest-c9226c3a0855/README':
                'This is a simple test repository for PMR2.\n',
            'pmr2hgtest-c9226c3a0855/file1':
                'This is file1.\n'
                'Yes there are changes.\n',
            'pmr2hgtest-c9226c3a0855/file2':
                'This is file2\n',
            'pmr2hgtest-c9226c3a0855/ext/import1/.hg_archival.txt':
                None,
            'pmr2hgtest-c9226c3a0855/ext/import1/.hgsub':
                'import2 = http://models.example.com/w/import2\n',
            'pmr2hgtest-c9226c3a0855/ext/import1/.hgsubstate':
                'a413e4d7eb3846209aa8df44addf625093aac231 import2\n',
            'pmr2hgtest-c9226c3a0855/ext/import1/README':
                'this is import1\n',
            'pmr2hgtest-c9226c3a0855/ext/import1/if1':
                'if1\n',
            'pmr2hgtest-c9226c3a0855/ext/import1/import2/.hg_archival.txt':
                None,
            'pmr2hgtest-c9226c3a0855/ext/import1/import2/README':
                'this is import2\n',
            'pmr2hgtest-c9226c3a0855/ext/import2/.hg_archival.txt':
                None,
            'pmr2hgtest-c9226c3a0855/ext/import2/README':
                'this is import2\n',
            'pmr2hgtest-c9226c3a0855/ext/import2/test':
                'New import2 feature\n',
        }
        self.archiver_tester(answers, 5)

    def test_205_ignore_subrepo(self):
        """\
        Test for archive that ignores subrepo
        """

        answers = {
            'pmr2hgtest-c9226c3a0855/.hg_archival.txt':
                None,
            'pmr2hgtest-c9226c3a0855/.hgsub':
                'ext/import1 = http://models.example.com/w/import1\n'
                'ext/import2 = http://models.example.com/w/import2\n',
            'pmr2hgtest-c9226c3a0855/.hgsubstate':
                '4df76eccfee8a0d27844b5c069bc399bb0e4e043 ext/import1\n'
                '60baac932b072c20fc7004c158ad2b1f5c80de14 ext/import2\n',
            'pmr2hgtest-c9226c3a0855/README':
                'This is a simple test repository for PMR2.\n',
            'pmr2hgtest-c9226c3a0855/file1':
                'This is file1.\n'
                'Yes there are changes.\n',
            'pmr2hgtest-c9226c3a0855/file2':
                'This is file2\n',
        }
        self.archiver_tester(answers, 5, False)


def test_suite():
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(DataTestCase))
    return suite

if __name__ == '__main__':
    unittest.main()
