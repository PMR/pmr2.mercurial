import unittest
import tempfile
import shutil
import os
import datetime
import tarfile
import zipfile
from os.path import basename, dirname, join
from logging import getLogger
from cStringIO import StringIO

logger = getLogger('pmr2.mercurial.tests')
imported = True

try:
    import zope.component
    import zope.interface
    from zope.app.component.hooks import getSiteManager
    from zope.publisher.browser import TestRequest

    from zope.configuration.xmlconfig import xmlconfig
    from zope.component.tests import clearZCML
except:
    logger.warn('One or more zope modules could not be imported; '
                'IStorage utility tests cannot commence.')
    imported = False

try:
    from pmr2.app.interfaces import IPMR2GlobalSettings
    from pmr2.app.workspace.exceptions import *
    from pmr2.app.workspace.interfaces import IWorkspace, IStorage
except:
    logger.warn('One or more pmr2.app modules could not be imported; '
                'IStorage utility tests cannot commence.')
    imported = False

import pmr2.mercurial
from pmr2.mercurial import *
from pmr2.mercurial.interfaces import *
from pmr2.mercurial.utility import *


class DummyWorkspace(object):
    zope.interface.implements(IWorkspace)
    def __init__(self, path):
        # Dummy value for use by the dummy settings object below.
        self.path = path
        self.storage = 'mercurial'

    @property
    def id(self):
        return basename(self.path)


class MercurialSettings(object):
    zope.interface.implements(IPMR2GlobalSettings)
    def dirCreatedFor(self, obj):
        return obj.path

    # dirOf is used by MercurialStorageUtility to acquire the path
    dirOf = dirCreatedFor


class UtilityTestCase(unittest.TestCase):

    def setUp(self):
        # XXX split this out into the setup decorator?
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

        self.date = str(datetime.date.today())

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

        self.fulllist = self.filelist + [self.nested_name]

        self.repo = Storage(self.repodir, ctx='tip')
        self.rev = self.repo.rev

        clearZCML()
        xmlconfig(open(join(pmr2.mercurial.__path__[0], 'configure.zcml')))

        # register custom utility that would have normally been done.
        sm = getSiteManager()
        sm.registerUtility(MercurialSettings(), IPMR2GlobalSettings)
        self.settings = zope.component.getUtility(IPMR2GlobalSettings)
        self.workspace = DummyWorkspace(self.repodir)

    def tearDown(self):
        shutil.rmtree(self.testdir)

    def test_000_storage(self):
        # Direct instantiation
        storage = MercurialStorage(self.workspace)
        self.assert_(IStorage.providedBy(storage))

    def test_001_utility(self):
        utility = MercurialStorageUtility()
        storage = utility(self.workspace)
        self.assert_(isinstance(storage, MercurialStorage))
        self.assert_(IStorage.providedBy(storage))

    def test_010_storage_base(self):
        storage = MercurialStorage(self.workspace)
        result = storage.files()
        self.assertEqual(result, self.fulllist)

    def test_101_storage_checkout(self):
        storage = MercurialStorage(self.workspace)
        storage.checkout(self.revs[0])
        result = storage.files()
        self.assertEqual(result, ['file1', 'file2',])

    def test_200_storage_log(self):
        storage = MercurialStorage(self.workspace)
        result = list(storage.log(self.revs[2], 2))
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['node'], self.revs[2])

    def test_201_storage_log(self):
        storage = MercurialStorage(self.workspace)
        result = list(storage.log(self.revs[2], 10))
        # XXX The following statement is NOT true as expected, as the
        # current way hgweb derives this will be as inclusive up to the
        # maximum number of revisions requested.
        # self.assertEqual(len(result), 3)
        # XXX This is currently true.
        self.assertEqual(len(result), 4)

    def test_250_storage_log_revnotfound(self):
        storage = MercurialStorage(self.workspace)
        self.assertRaises(RevisionNotFoundError, storage.log, 'xxxxxxxxxx', 10)
        self.assertRaises(RevisionNotFoundError, storage.log, 'abcdef1234', 10)

    def test_300_storage_file(self):
        storage = MercurialStorage(self.workspace)
        file = storage.file('file3')
        self.assertEqual(file, self.files[0])

    def test_301_storage_file(self):
        storage = MercurialStorage(self.workspace)
        storage.checkout(self.revs[0])
        file = storage.file('file1')
        self.assertEqual(file, self.files[0])

    def test_302_storage_file(self):
        storage = MercurialStorage(self.workspace)
        # just for fun.
        storage.checkout(self.revs[0])
        storage.checkout(self.revs[3])
        file = storage.file(self.nested_name)
        self.assertEqual(file, self.nested_file)

    def test_350_storage_file_not_found(self):
        storage = MercurialStorage(self.workspace)
        self.assertRaises(PathNotFoundError, storage.file, 'failepicfail')
        storage.checkout(self.revs[0])
        self.assertRaises(PathNotFoundError, storage.file, self.nested_name)
        self.assertRaises(PathNotFoundError, storage.file, 'file3')

    def test_400_fileinfo(self):
        storage = MercurialStorage(self.workspace)
        storage.checkout(self.revs[0])
        result = storage.fileinfo('file1')
        answer = {
            'author': 'user1 <1@example.com>',
            # standalone files has no permission value in hgweb
            # 'permissions': '-rw-r--r--',
            'permissions': '',
            'desc': 'added1',
            'node': self.revs[0],
            'date': result['date'],  # manual checking
            'size': len(self.files[0]),
            'basename': 'file1',
            'file': 'file1',
            'mimetype': result['mimetype'],
            'contents': result['contents'],
        }

        # XXX this test _may_ fail at around midnight as the test data
        # is created dynamically
        self.assert_(result['date'].startswith(self.date))
        self.assertEqual(answer, result)

    def test_500_listdir_root(self):
        storage = MercurialStorage(self.workspace)
        storage.checkout(self.revs[3])
        result = list(storage.listdir(''))
        answer = [
        {
            'author': '',
            'permissions': 'drwxr-xr-x',
            'desc': '',
            'node': self.revs[3],
            'date': result[0]['date'],
            'size': '',
            'basename': 'nested',
            'file': 'nested',
            'mimetype': result[0]['mimetype'],
            'contents': result[0]['contents'],
        },
        {
            'author': '',
            'permissions': '-rw-r--r--',
            'desc': 'added4',
            'node': self.revs[3],
            'date': result[1]['date'],
            'size': str(len(self.files[1])),
            'basename': 'file1',
            'file': 'file1',
            'mimetype': result[1]['mimetype'],
            'contents': result[1]['contents'],
        },
        {
            'author': '',
            'permissions': '-rw-r--r--',
            'desc': 'added4',
            'node': self.revs[3],
            'date': result[2]['date'],
            'size': str(len(self.files[1])),
            'basename': 'file2',
            'file': 'file2',
            'mimetype': result[2]['mimetype'],
            'contents': result[2]['contents'],
        },
        {
            'author': '',
            'permissions': '-rw-r--r--',
            'desc': 'added4',
            'node': self.revs[3],
            'date': result[3]['date'],
            'size': str(len(self.files[0])),
            'basename': 'file3',
            'file': 'file3',
            'mimetype': result[3]['mimetype'],
            'contents': result[3]['contents'],
        },
        ]
        self.assertEqual(answer, result)

    def test_501_listdir_root(self):
        storage = MercurialStorage(self.workspace)
        storage.checkout(self.revs[3])
        result = list(storage.listdir('nested'))
        answer = [
        {
            'author': '',
            'permissions': 'drwxr-xr-x',
            'desc': '',
            'node': self.revs[3],
            'date': result[0]['date'],
            'size': '',
            'basename': 'deep',
            'file': 'nested/deep',
            'mimetype': result[0]['mimetype'],
            'contents': result[0]['contents'],
        },
        ]
        self.assertEqual(answer, result)

    def test_502_listdir_nested_deep(self):
        storage = MercurialStorage(self.workspace)
        storage.checkout(self.revs[3])
        result = list(storage.listdir('nested/deep/dir'))
        answer = [
        {
            'author': '',
            'permissions': '-rw-r--r--',
            'desc': 'added4',
            'node': self.revs[3],
            'date': result[0]['date'],
            'size': str(len(self.nested_file)),
            'basename': 'file',
            'file': 'nested/deep/dir/file',
            'mimetype': result[0]['mimetype'],
            'contents': result[0]['contents'],
        },
        ]
        self.assertEqual(answer, result)

    def test_503_listdir_old_rev(self):
        storage = MercurialStorage(self.workspace)
        storage.checkout(self.revs[1])
        result = list(storage.listdir(''))
        answer = [
        {
            'author': '',
            'permissions': '-rw-r--r--',
            'desc': 'added2',
            'node': self.revs[1],
            'date': result[0]['date'],
            'size': str(len(self.files[1])),
            'basename': 'file1',
            'file': 'file1',
            'mimetype': result[0]['mimetype'],
            'contents': result[0]['contents'],
        },
        {
            'author': '',
            'permissions': '-rw-r--r--',
            'desc': 'added2',
            'node': self.revs[1],
            'date': result[1]['date'],
            'size': str(len(self.files[0])),
            'basename': 'file2',
            'file': 'file2',
            'mimetype': result[1]['mimetype'],
            'contents': result[1]['contents'],
        },
        ]
        self.assertEqual(answer, result)

    def test_510_listdir_onfile_fail(self):
        storage = MercurialStorage(self.workspace)
        storage.checkout(self.revs[0])
        self.assertRaises(PathNotDirError, storage.listdir, 'file1')
        self.assertRaises(PathNotDirError, storage.listdir, 'file2')
        storage.checkout(self.revs[3])
        self.assertRaises(PathNotDirError, storage.listdir, 'file3')
        self.assertRaises(PathNotDirError, storage.listdir, self.nested_name)

    def test_511_listdir_on_invalid_path(self):
        storage = MercurialStorage(self.workspace)
        storage.checkout(self.revs[0])
        self.assertRaises(PathNotFoundError, storage.listdir, 'file3')
        self.assertRaises(PathNotFoundError, storage.listdir, 'file11')
        storage.checkout(self.revs[3])
        self.assertRaises(PathNotFoundError, storage.listdir,
                          self.nested_name + 'asdf')
        self.assertRaises(PathNotFoundError, storage.listdir, 'nested/not')

    def test_600_pathinfo(self):
        storage = MercurialStorage(self.workspace)
        storage.checkout(self.revs[0])
        result = storage.pathinfo('file1')
        answer = {
            'author': 'user1 <1@example.com>',
            'permissions': '',
            'desc': 'added1',
            'node': self.revs[0],
            'date': result['date'],
            'size': len(self.files[0]),
            'basename': 'file1',
            'file': 'file1',
            'mimetype': result['mimetype'],
            'contents': result['contents'],
        }
        self.assertEqual(answer, result)
        self.assertEqual(result['mimetype'](), 'text/plain; charset=us-ascii')

    def test_601_pathinfo_nested_dir(self):
        storage = MercurialStorage(self.workspace)
        storage.checkout(self.revs[3])
        result = storage.pathinfo('nested/deep/dir')
        answer = {
            'author': '',
            'permissions': 'drwxr-xr-x',
            'desc': '',
            'node': self.revs[3],
            'date': '',
            'size': '',
            'basename': 'dir',
            'file': 'nested/deep/dir',
            'mimetype': result['mimetype'],
            'contents': result['contents'],
        }
        self.assertEqual(answer, result)

    def test_602_pathinfo_nested_dir(self):
        storage = MercurialStorage(self.workspace)
        storage.checkout(self.revs[3])
        result = storage.pathinfo(self.nested_name)
        answer = {
            'author': 'user3 <3@example.com>',
            'permissions': '',
            'desc': 'added4',
            'node': self.revs[3],
            'date': result['date'],
            'size': len(self.nested_file),
            'basename': 'file',
            'file': self.nested_name,
            'mimetype': result['mimetype'],
            'contents': result['contents'],
        }
        self.assertEqual(answer, result)

    def test_700_archiveFormats(self):
        storage = MercurialStorage(self.workspace)
        formats = storage.archiveFormats
        self.assertEqual(formats, ['tgz', 'zip',])

    def test_710_archiveInfo(self):
        storage = MercurialStorage(self.workspace)
        info = storage.archiveInfo('tgz')
        self.assertEqual(info, {
            'name': 'Tarball (gzipped)',
            'ext': '.tar.gz',
            'mimetype': 'application/x-tar',
        })
        info = storage.archiveInfo('zip')
        self.assertEqual(info, {
            'name': 'Zip File',
            'ext': '.zip',
            'mimetype': 'application/zip',
        })

    def test_720_archive_zip(self):
        storage = MercurialStorage(self.workspace)

        storage.checkout(self.revs[3])
        rev = self.revs[3][:12]
        root = '%s-%s' % (self.workspace.id, rev)
        names = ['file1', 'file2', 'file3', 'nested/deep/dir/file']
        contents = [self.files[1], self.files[1], self.files[0],
                    self.nested_file,]
        answer = zip(['%s/%s' % (root, n) for n in names], contents)

        archive = storage.archive('zip')
        stream = StringIO(archive)
        zfile = zipfile.ZipFile(stream, 'r')
        result = [i.filename for i in zfile.infolist()]

        for a, c in answer:
            self.assert_(a in result)
            self.assertEqual(zfile.read(a), c)

    def test_721_archive_zip(self):
        storage = MercurialStorage(self.workspace)

        storage.checkout(self.revs[0])
        rev = self.revs[0][:12]
        root = '%s-%s' % (self.workspace.id, rev)
        names = ['file1', 'file2']
        contents = [self.files[0], self.files[0],]
        answer = zip(['%s/%s' % (root, n) for n in names], contents)

        archive = storage.archive('zip')
        stream = StringIO(archive)
        zfile = zipfile.ZipFile(stream, 'r')
        result = [i.filename for i in zfile.infolist()]

        for a, c in answer:
            self.assert_(a in result)
            self.assertEqual(zfile.read(a), c)

    def test_730_archive_tgz(self):
        storage = MercurialStorage(self.workspace)

        storage.checkout(self.revs[3])
        rev = self.revs[3][:12]
        root = '%s-%s' % (self.workspace.id, rev)
        names = ['file1', 'file2', 'file3', 'nested/deep/dir/file']
        contents = [self.files[1], self.files[1], self.files[0],
                    self.nested_file,]
        answer = zip(['%s/%s' % (root, n) for n in names], contents)

        archive = storage.archive('tgz')
        stream = StringIO(archive)
        tfile = tarfile.open('test', 'r:gz', stream)
        result = [i.name for i in tfile.getmembers()]

        for a, c in answer:
            self.assert_(a in result)
            self.assertEqual(tfile.extractfile(a).read(), c)

    def test_731_archive_tgz(self):
        storage = MercurialStorage(self.workspace)

        storage.checkout(self.revs[0])
        rev = self.revs[0][:12]
        root = '%s-%s' % (self.workspace.id, rev)
        names = ['file1', 'file2']
        contents = [self.files[0], self.files[0],]
        answer = zip(['%s/%s' % (root, n) for n in names], contents)

        archive = storage.archive('tgz')
        stream = StringIO(archive)
        tfile = tarfile.open('test', 'r:gz', stream)
        result = [i.name for i in tfile.getmembers()]

        for a, c in answer:
            self.assert_(a in result)
            self.assertEqual(tfile.extractfile(a).read(), c)


def test_suite():
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    if imported:
        suite.addTest(makeSuite(UtilityTestCase))
    return suite

if __name__ == '__main__':
    unittest.main()
