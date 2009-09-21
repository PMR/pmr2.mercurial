from tarfile import TarFile
import unittest
import tempfile
import shutil
import os
from os.path import dirname, join, splitext

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


class PMR2Storage(object):
    zope.interface.implements(IPMR2StorageBase)
    def __init__(self, path):
        self.path = path
    def get_path(self):
        return self.path

class DataTestCase(unittest.TestCase):

    def setUp(self):
        self.archive_revs = [
            'eb2615b6ebf9a44226bba22c766bc7858e370ed9',
            'c7888f70e7ee440a561283bb7a27cc5ba9888a58',
        ]
        # setup/configure paths
        self.test_path = dirname(__file__)
        self.archive_name = 'pmr2hgtest.tgz'
        self.archive_path = join(self.test_path, self.archive_name)
        self.root_name = splitext(self.archive_name)[0]
        self.tempdir = tempfile.mkdtemp()

        self.import1 = 'import1'
        self.import1_path = join(self.tempdir, self.import1)

        self.import2 = 'import2'
        self.import2_path = join(self.tempdir, self.import2)

        # The structure of the repo follows
        # pmr2hgtest is the main archive
        # - first rev it imports nothing
        # - second rev it has import1 as subrepo
        # - third rev it adds import2 as subrepo
        # - forth rev it references updated import 1 and 2
        # import1 first rev imports nthing
        # - rev2 it imports 2

        # extraction 
        tf = TarFile.gzopen(self.archive_path)
        mem = tf.getmembers()
        for m in mem:
            tf.extract(m, self.tempdir)
        tf.close()

        # build test environ.
        self.repodir = join(self.tempdir, self.root_name)
        clearZCML()
        xmlconfig(open(join(pmr2.mercurial.__path__[0], 'configure.zcml')))

    def tearDown(self):
        shutil.rmtree(self.tempdir)

    def test_000_basic(self):
        o = PMR2Storage(self.repodir)
        r = TestRequest(rev=self.archive_revs[0], request_subpath=('file1',))
        a = zope.component.queryMultiAdapter((o, r,), name="PMR2StorageRequest")
        self.assertEqual(self.archive_revs[0], a.rev)
        files = a.raw_manifest().keys()
        files.sort()
        self.assertEqual(files, ['README', 'file1',], 
            'internal changeset context have been changed?')

    def test_001_archive(self):
        """\
        Standard archive test.
        """

        o = PMR2Storage(self.repodir)
        r = TestRequest(rev=self.archive_revs[0], request_subpath=('gz',))
        a = zope.component.queryMultiAdapter((o, r,), name="PMR2StorageRequest")
        out = StringIO(a.archive())
        out.seek(0)
        testtf = TarFile.gzopen('', fileobj=out)
        names = [i.name for i in testtf.getmembers()]
        names.sort()
        answers = [
            'pmr2hgtest-eb2615b6ebf9/.hg_archival.txt',
            'pmr2hgtest-eb2615b6ebf9/README',
            'pmr2hgtest-eb2615b6ebf9/file1',
        ]
        self.assertEqual(names, answers)
        # XXX can't test response headers because test response provides
        # limited features

    def test_002_archive(self):
        """\
        Include import archive test.
        """

        o = PMR2Storage(self.repodir)
        r = TestRequest(rev=self.archive_revs[1], request_subpath=('gz',))
        a = zope.component.queryMultiAdapter((o, r,), name="PMR2StorageRequest")
        out = StringIO(a.archive())
        out.seek(0)
        testtf = TarFile.gzopen('', fileobj=out)
        names = [i.name for i in testtf.getmembers()]
        names.sort()
        answers = [
            'pmr2hgtest-eb2615b6ebf9/.hg_archival.txt',
            'pmr2hgtest-eb2615b6ebf9/README',
            'pmr2hgtest-eb2615b6ebf9/ext/import1/README',
            'pmr2hgtest-eb2615b6ebf9/file1',
        ]
        self.assertEqual(names, answers, 'subrepo missing?')


def test_suite():
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(DataTestCase))
    return suite

if __name__ == '__main__':
    unittest.main()
