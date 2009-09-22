import tarfile
import unittest
import tempfile
import shutil
import os
from os.path import basename, dirname, join, splitext

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

import Acquisition

# Lightweight helper objects

class Location(object):
    def __init__(self, name):
        self.__name__ = name

class Folder(Location, Acquisition.Implicit):
    def __init__(self, id_):
        super(Folder, self).__init__(id_)
        self.d = {}
    def __of__(self, other):
        other.__setitem__(self.__name__, self)
        return super(Folder, self).__of__(other)
    def __setitem__(self, key, value):
        self.d[key] = value
    def __getitem__(self, key):
        return self.d[key]

class PMR2Storage(Folder):
    zope.interface.implements(IPMR2StorageBase)
    def __init__(self, path):
        Folder.__init__(self, basename(path))
        self.path = path
    def absolute_url(self):
        baseuri = 'http://models.example.com/w/'
        return baseuri + basename(self.path)
    def get_path(self):
        return self.path


class DataTestCase(unittest.TestCase):

    def setUp(self):
        self.archive_revs = [
            'eb2615b6ebf9a44226bba22c766bc7858e370ed9',
            'c7888f70e7ee440a561283bb7a27cc5ba9888a58',
            'd52a32a5fa62a357ed77314888b939f0fc7c9c9b',
            'd2759ae2454c4e0946f4d8feee60864590b2ddb0',
            '0ab9d678be937c20c3ba4953ba49515fdad396e7',
            'c9226c3a085546313d61413adb95d3a9da2294e0',
        ]
        # setup/configure paths
        self.test_path = dirname(__file__)
        self.archive_name = 'pmr2hgtest.tgz'
        self.archive_path = join(self.test_path, self.archive_name)
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

        # extraction 
        tf = tarfile.open(self.archive_path, 'r:gz')
        mem = tf.getmembers()
        for m in mem:
            tf.extract(m, self.tempdir)
        tf.close()

        # build test environ.
        self.repodir = join(self.tempdir, self.root_name)
        clearZCML()
        xmlconfig(open(join(pmr2.mercurial.__path__[0], 'configure.zcml')))

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

    def archiver_tester(self, answers, id_):
        """\
        The core archive tester.
        """

        o = self.pmr2hgtest
        r = TestRequest(rev=self.archive_revs[id_], request_subpath=('gz',))
        a = zope.component.queryMultiAdapter((o, r,), name="PMR2StorageRequest")
        out = a.archive()
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


def test_suite():
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(DataTestCase))
    return suite

if __name__ == '__main__':
    unittest.main()
