import unittest
import tempfile
import shutil
import os
from os.path import dirname, join
from pmr2.mercurial import Storage, Sandbox

class RepositoryInitTestCase(unittest.TestCase):

    def setUp(self):
        self.repodir = tempfile.mkdtemp()
        
    def tearDown(self):
        shutil.rmtree(self.repodir)

    def test_init_failed(self):
        # testing init would fail on a directory not managed by hg
        self.assertRaises(ValueError, Storage, self.repodir)

    def test_create_failed(self):
        # existing directory
        self.assertRaises(ValueError, Storage.create, self.repodir)
        # invalid location
        self.assertRaises(ValueError, Storage.create, '/dev/null', False)

    def test_create_success1(self):
        result = Storage.create(self.repodir, False)
        self.assert_(result, 'Storage not created')

    def test_create_success2(self):
        result = Storage.create(self.repodir + '/test', True)
        self.assert_(result, 'Storage not created')

    def test_init_success(self):
        Storage.create(self.repodir, False)
        store = Storage(self.repodir)
        self.assert_(isinstance(store, Storage))


class RepositoryTestCase(unittest.TestCase):

    def setUp(self):
        self.repodir = tempfile.mkdtemp()
        Storage.create(self.repodir, False)
        self.workspace = Storage(self.repodir)
        
    def tearDown(self):
        shutil.rmtree(self.repodir)

    def test_changectx(self):
        # do we need this test?
        ctx = self.workspace._changectx('tip')  # as 'default' not exist yet
        self.assertNotEqual(ctx, None, msg='failed to get context')
        self.assertEqual(ctx.branch(), 'default', msg='unexpected context')

    def test_manifest_empty(self):
        # empty manifest
        result = [i for i in self.workspace.manifest('tip')]
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['path'], '/')


class SandboxTestCase(unittest.TestCase):

    def setUp(self):
        self.repodir = tempfile.mkdtemp()
        Sandbox.create(self.repodir, False)
        self.sandbox = Sandbox(self.repodir, ctx='tip')
        self.path = dirname(__file__)
        self.filelist = ['file1', 'file2', 'file3',]
        self.files = [open(join(self.path, i)).read() for i in self.filelist]
        self.msg = 'added some files'
        self.user = 'Tester <test@example.com>'
        
    def tearDown(self):
        shutil.rmtree(self.repodir)

    def test_add_file_content_fail(self):
        self.assertRaises(ValueError, self.sandbox.add_file_content, 
                          '../notexistfile', '')

    def test_commit_fail(self):
        self.assertRaises(ValueError, self.sandbox.commit, '', '')
        self.assertRaises(ValueError, self.sandbox.commit, 'm', '')
        self.assertRaises(ValueError, self.sandbox.commit, '', 'm')

    def test_file_modification(self):
        # testing file adding features

        def zipdict(st):
            changetypes = (
                'modified', 'added', 'removed', 'deleted', 'unknown', 
                'ignored', 'clean',
            )
            return dict(zip(changetypes, st))

        self.sandbox.add_file_content('file1', self.files[0])
        self.sandbox.add_file_content('file2', self.files[1])
        # XXX - accessing private attributes
        status = zipdict(self.sandbox._repo.status())
        self.assertEqual(status['added'], ['file1', 'file2',])
        self.sandbox.commit(self.msg, self.user)
        # XXX - accessing private attributes
        status = zipdict(self.sandbox._repo.status(
                list_ignored=True, list_clean=True))
        self.assertEqual(status['clean'], ['file1', 'file2',])

    def test_status(self):
        self.sandbox.add_file_content('file1', self.files[0])
        self.sandbox.add_file_content('file2', self.files[1])
        self.sandbox.commit(self.msg, self.user)
        self.sandbox.add_file_content('file2', self.files[2])
        self.sandbox.add_file_content('file3', self.files[2])
        stat = [i for i in self.sandbox.status()]
        fent = [i for i in stat[0]['fentries']()]
        self.assertEqual(len(fent), 3, 'number of file entries != 3')


if __name__ == '__main__':
    unittest.main()
