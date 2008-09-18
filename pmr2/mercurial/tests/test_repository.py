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
        # existing file
        invalid = tempfile.mkstemp()[1]
        self.assertRaises(ValueError, Storage.create, invalid, False)
        os.unlink(invalid)

    def test_create_success1(self):
        result = Storage.create(self.repodir, False)
        self.assert_(result, 'Storage not created')

    def test_create_success2(self):
        result = Storage.create(join(self.repodir, 'test'), True)
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
        # tests for exceptions raised by addition of file content.
        # this resolves to full path for failure
        pd = os.pardir
        elsewhere = tempfile.mktemp()
        outside = os.path.abspath(join(os.curdir, 'outside'))
        invalidpath = join(pd, 'invalidpath')
        invalidpath2 = join('a', 'b', pd, pd, pd, 'invalidpath')
        paths = (elsewhere, outside, invalidpath, invalidpath2,)
        for i in paths:
            self.assertRaises(ValueError, self.sandbox.add_file_content, i, '')

    def test_add_file_content_success(self):
        # testing adding of file.
        def add(fn, oc):
            self.sandbox.add_file_content(fn, self.repodir)
            self.sandbox.add_file_content(fn, oc)
            fc = open(os.path.join(self.repodir, fn)).read()
            self.assertEqual(oc, fc, 'file content mismatch')

        add('file1', '1')
        add(join('d', 'file1',), 'in a dir')
        add(join('a', 'b', 'c', 'd', 'e', 'file1',), 'this is totally nested')

    def test_commit_fail(self):
        # commit failing due to missing required values
        self.assertRaises(ValueError, self.sandbox.commit, '', '')
        self.assertRaises(ValueError, self.sandbox.commit, 'm', '')
        self.assertRaises(ValueError, self.sandbox.commit, '', 'm')

    def test_commit_success(self):
        self.sandbox.add_file_content('file1', self.files[0])
        self.sandbox.commit(self.msg, self.user)
        # private
        status = statdict(self.sandbox._repo.status(
                list_ignored=True, list_clean=True))
        self.assertEqual(status['clean'], ['file1'])

    def test_file_modification(self):
        # testing file adding features

        self.sandbox.add_file_content('file1', self.files[0])
        self.sandbox.add_file_content('file2', self.files[1])
        # XXX - accessing private attributes for verification
        status = statdict(self.sandbox._repo.status())
        self.assertEqual(status['added'], ['file1', 'file2',])
        self.sandbox.commit(self.msg, self.user)
        # XXX - accessing private attributes for verification
        status = statdict(self.sandbox._repo.status(
                list_ignored=True, list_clean=True))
        self.assertEqual(status['clean'], ['file1', 'file2',])

    def test_mkdir(self):
        # invalid parent path
        self.assertRaises(ValueError, self.sandbox.mkdir, join(os.pardir, '1'))

        # outside repo
        fakedir = tempfile.mkdtemp()
        self.assertRaises(ValueError, self.sandbox.mkdir, fakedir)
        shutil.rmtree(fakedir)

        self.assert_(self.sandbox.mkdir('1'))
        self.assert_(self.sandbox.mkdir(join('1', '2')))
        self.assert_(self.sandbox.mkdir(join('3', '2', '1')))
        # redoing it will be fine.
        self.assert_(self.sandbox.mkdir(join('3', '2', '1')))
        self.assert_(self.sandbox.mkdir(join('3', '2')))
        # new nested
        self.assert_(self.sandbox.mkdir(join('3', '2', '2')))

        self.assert_(os.path.isdir(os.path.join(self.repodir, join('1', '2'))))
        self.assert_(os.path.isdir(os.path.join(self.repodir, join('3', '2'))))

    def test_status(self):
        self.sandbox.add_file_content('file1', self.files[0])
        self.sandbox.add_file_content('file2', self.files[1])
        self.sandbox.commit(self.msg, self.user)
        self.sandbox.add_file_content('file2', self.files[2])
        self.sandbox.add_file_content('file3', self.files[2])
        stat = [i for i in self.sandbox.status()]
        fent = [i for i in stat[0]['fentries']()]
        # XXX could use more validation here based on below
        # print '%s\n%s\n' % (stat, fent)
        self.assertEqual(len(fent), 3, 'number of file entries != 3')

    def test_source_check(self):
        self.assertRaises(TypeError,
                self.sandbox._source_check, None)
        self.assertRaises(TypeError,
                self.sandbox._source_check, [None])

    def test_filter_paths(self):
        """\
        this test will verify that the private method _filter_paths will
        filter out paths within the repo that are invalid by either not
        exist or not within the repository.
        """

        pd = os.pardir
        self.assertEqual(self.sandbox._filter_paths(
                [
                    join('test', pd, pd, 'outside'), 
                    tempfile.gettempdir(),
                    'nonexist',
                ]
            ), [])

    def test_rename_file_failure(self):

        pd = os.pardir
        ps = os.pathsep
        self.sandbox.add_file_content('file1', self.files[0])
        # destination not in repo
        self.assertRaises(ValueError,
                self.sandbox.rename, 'file1', join(pd, 'move1'))
        # invalid type for dest
        self.assertRaises(TypeError,
                self.sandbox.rename, 'file1', None)
        self.assertRaises(TypeError,
                self.sandbox.rename, 'file1', [join(pd, 'move1')])

        # can't overwrite file
        self.sandbox.add_file_content('move1', self.files[0])
        self.assertRaises(ValueError,
                self.sandbox.rename, ['file1'], 'move1')
        self.sandbox.add_file_content('file2', self.files[0])
        self.assertRaises(ValueError,
                self.sandbox.rename, ['file1', 'file2'], 'move1')
        self.assertRaises(ValueError,
                self.sandbox.rename, ['file1', 'file2'],
                join('move1', 'move2'))
        # no valid source
        # XXX meant to get to root
        self.assertRaises(ValueError,
                self.sandbox.rename, [ps + 'file1', ps + 'file2'], 'move2')

    def test_remove_file(self):
        for i, x in enumerate(self.filelist):
            self.sandbox.add_file_content(self.filelist[i], self.files[i])
        n1 = join('z', 'x', 'y', '1')
        self.sandbox.add_file_content(n1, 'nested file')
        self.sandbox.commit(self.msg, self.user)

        nested = [join('d', i) for i in self.filelist]
        for i, x in enumerate(self.filelist):
            self.sandbox.add_file_content(nested[i], self.files[i])

        # make one modified
        self.sandbox.add_file_content(self.filelist[0], 'wiped')

        clean = self.filelist[1:] + [n1]
        clean.sort()

        n2 = join('z', 'x', 'y', '2')
        self.sandbox.add_file_content(n2, 'nested file')
        added = nested + [n2]
        added.sort()

        modified = self.filelist[:1]

        # private _repo
        status = statdict(self.sandbox._repo.status(
                list_ignored=True, list_clean=True))
        # check status
        self.assertEqual(status['clean'], clean)
        self.assertEqual(status['modified'], modified)
        self.assertEqual(status['added'], added)

        # 1 modified, 2 clean, 1 new
        test1 = self.filelist + [n2]
        self.sandbox.remove(test1)

        # private _repo
        status = statdict(self.sandbox._repo.status(
                list_ignored=True, list_clean=True))

        # added item should never show up
        self.assert_(not os.path.exists(self.sandbox._fullpath(n2)))
        self.assertEqual(status['deleted'], self.filelist)

        # 1 commited and 3 clean (should be the rest)
        test2 = [n1] + nested
        self.sandbox.remove(test2)

        # private _repo
        status = statdict(self.sandbox._repo.status(
                list_ignored=True, list_clean=True))

        fl = test1 + test2
        # this method will return nothing as all the paths will be 
        # removed.  see self.test_filter_paths
        self.assertEqual(
            self.sandbox._filter_paths(fl),
            [],
        )
        self.assert_(not os.path.exists(self.sandbox._fullpath('d')))

        fl = []

        nested = [join('e', i) for i in self.filelist]
        for i, x in enumerate(self.filelist):
            self.sandbox.add_file_content(nested[i], self.files[i])
        fl += nested

        nested = [join('e', 'f' , i) for i in self.filelist]
        for i, x in enumerate(self.filelist):
            self.sandbox.add_file_content(nested[i], self.files[i])
        fl += nested

        fl.sort()

        self.sandbox.commit(self.msg, self.user)
        self.sandbox.remove(['e'])
        self.assert_(not os.path.exists(self.sandbox._fullpath('e')))

        status = statdict(self.sandbox._repo.status(
                list_ignored=True, list_clean=True))
        status['deleted'] = fl

    def test_rename_file_success(self):
        self.sandbox.add_file_content('file1', self.files[0])
        errs, copied = self.sandbox.rename('file1', 'move1')
        self.assertEqual(errs, 0)
        # private _repo
        status = statdict(self.sandbox._repo.status())
        # copied results are lists of tuples, first item is basename
        self.assertEqual(copied[0][0], 'file1')
        self.assertEqual(status['added'], ['move1',])
        self.sandbox.commit(self.msg, self.user)

        errs, copied = self.sandbox.rename('move1', 'move2')
        # private _repo
        status = statdict(self.sandbox._repo.status())
        self.assertEqual(status['removed'], ['move1',])
        self.assertEqual(status['added'], ['move2',])

        t = join('dir', 'move3')
        errs, copied = self.sandbox.rename('move2', t)
        # private _repo
        status = statdict(self.sandbox._repo.status())
        self.assertEqual(status['added'], [t,])

        self.sandbox.add_file_content(self.filelist[0], self.files[0])
        self.sandbox.add_file_content(self.filelist[1], self.files[1])
        self.sandbox.add_file_content(self.filelist[2], self.files[2])
        self.sandbox.commit(self.msg, self.user)

        u = join('dir', 'move4')
        self.sandbox.add_file_content(u, self.files[0])
        errs, copied = self.sandbox.rename('dir', 'dir2')
        old_t = t
        t = join('dir2', 'move3')
        u = join('dir2', 'move4')
        nl = [t, u,]
        status = statdict(self.sandbox._repo.status())
        self.assertEqual(status['added'], nl)

        nd = join('some', 'nested', 'dir')
        errs, copied = self.sandbox.rename(self.filelist, nd)
        # private _repo
        status = statdict(self.sandbox._repo.status())
        self.assertEqual(status['added'], 
                nl + [join(nd, i) for i in self.filelist])
        self.assertEqual(status['removed'], [old_t] + self.filelist)

    def test_rename_file_other(self):
        self.sandbox.add_file_content('file1', self.files[0])
        self.sandbox.add_file_content('file2', self.files[0])
        self.sandbox.add_file_content('file3', self.files[0])
        self.sandbox.commit(self.msg, self.user)
        errs, copied = self.sandbox.rename(['file1', 'file2', 'file3'], 'move1')
        self.assertEqual(errs, 0)
        errs, copied = self.sandbox.rename(
            [
                join('move1', 'file1'),
                join('move1', 'file2'),
                join('move2', 'file3'),
            ],  # move2/file3
            '',  # empty = root
        )
        self.assertEqual(errs, 1)

    def test_delete_file(self):
        pass


def statdict(st):
    # build a stat dictionary
    changetypes = (
        'modified', 'added', 'removed', 'deleted', 'unknown', 
        'ignored', 'clean',
    )
    return dict(zip(changetypes, st))


if __name__ == '__main__':
    unittest.main()
