import unittest
import tempfile
import shutil
import os
from os.path import dirname, join

from pmr2.mercurial import *
from pmr2.mercurial.exceptions import *

class RepositoryInitTestCase(unittest.TestCase):

    def setUp(self):
        self.repodir = tempfile.mkdtemp()
        
    def tearDown(self):
        shutil.rmtree(self.repodir)

    def test_init_failed(self):
        # testing init would fail on a directory not managed by hg
        self.assertRaises(PathInvalid, Storage, self.repodir)

    def test_create_failed(self):
        # existing directory
        self.assertRaises(PathExists, Storage.create, self.repodir)
        # existing file, causing path to be invalid.
        tf = tempfile.mkstemp()
        os.close(tf[0])  # close the descriptor that was opened above
        invalid = tf[1]
        invalid2 = join(invalid, 'nested')
        invalid3 = join(invalid, 'nested', 'evendeeper')
        self.assertRaises(PathInvalid, Storage.create, invalid, False)
        self.assertRaises(PathInvalid, Storage.create, invalid2, False)
        # try to create a new one
        self.assertRaises(PathInvalid, Storage.create, invalid3, True)
        os.unlink(invalid)

    def test_create_success1(self):
        result = Storage.create(self.repodir, False)
        self.assert_(result, 'Storage not created')

    def test_create_success2(self):
        result = Storage.create(join(self.repodir, 'test'), True)
        self.assert_(result, 'Storage not created')
        result = Storage.create(join(self.repodir, 'test2', 'deeper'), True)
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
        ctx0 = self.workspace._changectx('tip')  # as 'default' not exist yet
        ctx1 = self.workspace._changectx()  # should also get tip
        self.assertEqual(ctx0.node(), ctx1.node())
        self.assertNotEqual(ctx0, None, msg='failed to get context')
        self.assertEqual(ctx0.branch(), 'default', msg='unexpected context')
        self.assertRaises(RevisionNotFound, self.workspace._changectx, 'fail')

    def test_manifest_empty(self):
        # empty manifest
        self.assertRaises(RepoEmpty, self.workspace.manifest, 'tip')
        self.assertRaises(PathNotFound, 
                self.workspace.manifest, 'tip', path='no')


class RepositorySandboxTestCase(unittest.TestCase):

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

    def test_file(self):
        log = [i for i in self.repo.log().next()['entries']()]
        f = self.repo.file(path='file1')
        self.assertEqual(f, self.files[1])
        # older version
        f = self.repo.file(rev=log[2]['node'], path='file1')
        self.assertEqual(f, self.files[0])

    def test_fileinfo_failure(self):
        self.assertRaises(PathNotFound, self.repo.fileinfo, path='file4')

    def test_fileinfo_success(self):
        log = [i for i in self.repo.log().next()['entries']()]
        f = self.repo.fileinfo(path='file1').next()
        self.assertEqual(f['file'], 'file1')
        # older version
        f = self.repo.fileinfo(rev=log[2]['node'], path='file1').next()
        self.assertEqual(f['file'], 'file1')
        self.assertEqual(f['node'], log[2]['node'])


class SandboxTestCase(unittest.TestCase):

    def setUp(self):
        self.testdir = tempfile.mkdtemp()
        self.repodir = join(self.testdir, 'repodir')
        Sandbox.create(self.repodir, True)
        self.sandbox = Sandbox(self.repodir, ctx='tip')
        self.path = dirname(__file__)
        self.filelist = ['file1', 'file2', 'file3',]
        self.files = [open(join(self.path, i)).read() for i in self.filelist]
        self.msg = 'added some files'
        self.user = 'Tester <test@example.com>'
        
    def tearDown(self):
        shutil.rmtree(self.testdir)

    def _demo(self):
        self.sandbox.add_file_content('file1', self.files[0])
        self.sandbox.add_file_content('file2', self.files[0])
        self.sandbox.commit('added1', 'user1 <1@example.com>')
        self.sandbox.add_file_content('file1', self.files[1])
        self.sandbox.commit('added2', 'user2 <2@example.com>')
        self.sandbox.add_file_content('file2', self.files[1])
        self.sandbox.add_file_content('file3', self.files[0])
        self.sandbox.commit('added3', 'user3 <3@example.com>')

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
            self.assertRaises(PathInvalid, self.sandbox.add_file_content, i, '')

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

    def test_branches(self):
        self._demo()
        self.assertEqual(self.sandbox.branches().keys(), ['default'])

    def test_clone_fail(self):
        # Testing clone down here because we need sandbox to create data
        self.assertRaises(TypeError, self.sandbox.clone, None)
        fakedir = tempfile.mkdtemp()
        # can't overwrite any existing destination.
        self.assertRaises(PathExists, self.sandbox.clone, fakedir)
        os.rmdir(fakedir)

    def test_clone_success(self):
        # Testing clone down here because we need sandbox to create data
        # depends on manifest working

        self._demo()
        dest = [join(self.testdir, str(i)) for i in xrange(4)]
        self.sandbox.clone(dest[0])
        repo0 = Storage(dest[0])
        
        # nested
        dest[1] = join(dest[1], '1', '2', '3')
        repo0.clone(dest[1])

        repo1 = Storage(dest[1])
        m0 = repo0.manifest().next()['node']
        m1 = repo1.manifest().next()['node']
        self.assertEqual(m0, m1, 'revision mismatch between clone')

        # validate working copy is cloned properly.
        f0 = open(join(repo0._path, 'file3')).read()
        f1 = open(join(repo1._path, 'file3')).read()
        self.assertEqual(f0, f1,
                'file content in working copy mismatch between clone')

        # definitely not an existing rev
        self.assertRaises(RevisionNotFound, repo1.clone, dest[2], ['zzz'])

        # cloning up to an existing rev
        node = repo1._repo.changelog.node(1)
        repo1.clone(dest[2], node)
        repo2 = Storage(dest[2])
        self.assertEqual(repo2._repo.changelog.count(), 2)
        #self.sandbox.add_file_content('file1', self.files[1])  # rev1
        ff = open(join(repo2._path, 'file1')).read()
        self.assertEqual(ff, self.files[1],
                'file content in working copy mismatch between clone')
        #self.sandbox.add_file_content('file2', self.files[0])  # rev0
        ff = open(join(repo2._path, 'file2')).read()
        self.assertEqual(ff, self.files[0],
                'file content in working copy mismatch between clone')

        # test no update
        repo1.clone(dest[3], node, update=False)
        repo3 = Storage(dest[3])
        # file should not exist.
        self.assert_(not os.path.exists(join(repo3._path, 'file1')))

    def test_commit_fail(self):
        # commit failing due to missing required values
        self.assertRaises(ValueError, self.sandbox.commit, '', '')
        self.assertRaises(ValueError, self.sandbox.commit, 'm', '')
        self.assertRaises(ValueError, self.sandbox.commit, '', 'm')

    def test_commit_success(self):
        self.sandbox.add_file_content('file1', self.files[0])
        self.sandbox.commit(self.msg, self.user)
        node1 = self.sandbox._ctx.node()
        self.sandbox.add_file_content('file1', self.files[1])
        self.sandbox.commit(self.msg, self.user)
        node2 = self.sandbox._ctx.node()
        # private
        status = statdict(self.sandbox._repo.status(
                list_ignored=True, list_clean=True))
        self.assertEqual(status['clean'], ['file1'])
        self.assertNotEqual(node1, node2, 'internal context not updated')

    def test_current_branch(self):
        self._demo()
        self.assertEqual('default', self.sandbox.current_branch())

    def test_file(self):
        # this tests fetching of updated files.
        self._demo()
        self.sandbox.add_file_content('file3', self.files[1])
        f = self.sandbox.file(path='file3')
        self.assertEqual(f, self.files[1])

    def test_fileinfo_failure(self):
        self._demo()
        self.assertRaises(PathNotFound, self.sandbox.fileinfo, path='file4')

    def test_fileinfo_success(self):
        self._demo()
        self.sandbox.add_file_content('file1', self.files[2])
        f = self.sandbox.fileinfo(path='file1').next()
        self.assertEqual(f['file'], 'file1')

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

    def test_log(self):
        self._demo()
        loggen = self.sandbox.log()
        log = [i for i in loggen.next()['entries']()]
        # not really needing a test here, since currently it's based
        # on the hgweb directly.
        self.assertEqual(log[0]['desc'], 'added3')
        self.assertEqual(log[0]['author'], 'user3 <3@example.com>')
        self.assertEqual(log[2]['desc'], 'added1')
        self.assertEqual(log[2]['author'], 'user1 <1@example.com>')
        loggen = self.sandbox.log(shortlog=True)
        log2 = [i for i in loggen.next()['entries']()]
        # log is short enough
        self.assertEqual(len(log), len(log2))
        loggen = self.sandbox.log(limit=1, shortlog=True)
        log3 = [i for i in loggen.next()['entries']()]
        self.assertEqual(len(log3), 1)

    def test_manifest(self):
        self._demo()
        n0 = str(self.sandbox.manifest().next()['node'])
        c0 = self.sandbox._ctx.node()
        self._demo()
        n1 = str(self.sandbox.manifest().next()['node'])
        c1 = self.sandbox._ctx.node()
        self.assertNotEqual(c0, c1)
        self.assertNotEqual(n0, n1, 'hgweb not updated')

    def test_mkdir(self):
        # invalid parent path
        self.assertRaises(PathInvalid, self.sandbox.mkdir, join(os.pardir, '1'))

        # outside repo
        fakedir = tempfile.mkdtemp()
        self.assertRaises(PathInvalid, self.sandbox.mkdir, fakedir)
        os.rmdir(fakedir)

        self.assert_(self.sandbox.mkdir('1'))
        self.assert_(self.sandbox.mkdir(join('1', '2')))
        self.assert_(self.sandbox.mkdir(join('3', '2', '1')))
        # redoing it will be fine.
        self.assert_(self.sandbox.mkdir(join('3', '2', '1')))
        self.assert_(self.sandbox.mkdir(join('3', '2')))
        # new nested
        self.assert_(self.sandbox.mkdir(join('3', '2', '2')))

        self.assert_(os.path.isdir(join(self.repodir, join('1', '2'))))
        self.assert_(os.path.isdir(join(self.repodir, join('3', '2'))))

    def test_pull_failure(self):
        self._demo()
        # fail on no valid source.
        self.assertRaises(RepoNotFound, self.sandbox.pull)

    def test_pull_success(self):
        # Testing pulling
        self._demo()
        dest = [join(self.testdir, str(i)) for i in xrange(3)]
        self.sandbox.clone(dest[0])
        source = self.sandbox
        target = Sandbox(dest[0])

        source.add_file_content('file3', 'weird new content for file3')
        source.add_file_content('file4', 'file4 new')
        source.commit('added4', 'user4 <4@example.com>')

        # pull the new stuff from source to target
        heads = target.pull(source._path)
        self.assertEqual(heads, 1)
        # should automatically update working directory.
        self.assert_(os.path.exists(join(target._path, 'file4')),
                     'target working dir not updated')

        # reinitialize source
        m0 = source.manifest().next()['node']
        m1 = target.manifest().next()['node']
        self.assertEqual(m0, m1, 'commit id mismatch')

        source.add_file_content('file1', 'source')
        source.add_file_content('file2', 'add')
        source.add_file_content('newsource', 'add')
        source.commit('sourceadd', 'user4 <4@example.com>')

        target.add_file_content('file1', 'target')
        target.add_file_content('file2', 'add')
        target.commit('targetadd', 'user4 <4@example.com>')

        heads = target.pull(source._path)

        t = open(join(target._path, 'file1')).read()
        self.assertEqual(t, 'target', 'target working dir overwritten!')
        self.assert_(not os.path.exists(join(target._path, 'newsource')))

        self.assert_(heads > 1)

        m2 = source.manifest().next()['node']
        m3 = target.manifest().next()['node']
        self.assertNotEqual(m2, m3) 
        self.assertNotEqual(m1, m3)  # it really should have been updated.
        self.assertNotEqual(m0, m2)  # it really should have been updated.

    def test_push_failure(self):
        self._demo()
        # push nowhere
        self.assertRaises(RepoNotFound, self.sandbox.push)

        dest = [join(self.testdir, str(i)) for i in xrange(3)]
        self.sandbox.clone(dest[0])
        source = self.sandbox
        target = Sandbox(dest[0])

        source.add_file_content('file1', 'source')
        source.add_file_content('file2', 'add')
        source.add_file_content('newsource', 'add')
        source.commit('sourceadd', 'user4 <4@example.com>')

        target.add_file_content('file1', 'target')
        target.add_file_content('file2', 'add')
        target.commit('targetadd', 'user4 <4@example.com>')

        # multiple heads.
        result = target.push()
        self.assert_(not result)

        # forcing should work
        result = target.push(force=True)
        self.assert_(result)

    def test_push_success(self):
        self._demo()
        # push nowhere
        self.assertRaises(RepoNotFound, self.sandbox.push)

        dest = [join(self.testdir, str(i)) for i in xrange(3)]
        self.sandbox.clone(dest[0])
        source = self.sandbox
        target = Sandbox(dest[0])

        target.add_file_content('file1', 'source')
        target.add_file_content('file2', 'add')
        target.add_file_content('newsource', 'add')
        target.commit('tar1', 'user4 <4@example.com>')

        target.add_file_content('file1', 'newer')
        target.add_file_content('file2', 'adding')
        target.commit('tar2', 'user4 <4@example.com>')

        result = target.push()
        self.assert_(result)

    def test_status(self):
        # should not fail.
        stat = [i for i in self.sandbox.status()]
        fent = [i for i in stat[0]['fentries']()]
        self.assertEqual(len(fent), 0)
        self.assertEqual(stat[0][''], 'status')

        self.sandbox.add_file_content('file1', self.files[0])
        self.sandbox.add_file_content('file2', self.files[1])
        self.sandbox.add_file_content('zzz/sleep', self.files[1])
        self.sandbox.commit(self.msg, self.user)
        self.sandbox.add_file_content('file2', self.files[2])
        self.sandbox.add_file_content('file3', self.files[2])
        stat = [i for i in self.sandbox.status()]
        fent = [i for i in stat[0]['fentries']()]
        dent = [i for i in stat[0]['dentries']()]
        # print '%s\n%s\n%s\n' % (stat, fent, dent)
        self.assertEqual(len(fent), 3)
        self.assertEqual(len(dent), 1)
        self.assertEqual(fent[0]['file'], 'file1')
        self.assertEqual(fent[0]['status'], 'clean')
        self.assertEqual(fent[0]['size'], len(self.files[0]))
        self.assertEqual(fent[1]['file'], 'file2')
        self.assertEqual(fent[1]['status'], 'modified')
        self.assertEqual(fent[1]['size'], len(self.files[2]))
        self.assertEqual(fent[2]['file'], 'file3')
        self.assertEqual(fent[2]['status'], 'added')
        self.assertEqual(fent[2]['size'], len(self.files[2]))
        self.assertEqual(dent[0]['path'], '/zzz/')

        stat = [i for i in self.sandbox.status(path='zzz')]
        fent = [i for i in stat[0]['fentries']()]
        # print '%s\n%s\n' % (stat, fent)
        self.assertEqual(fent[0]['file'], 'zzz/sleep')
        self.assertEqual(fent[0]['basename'], 'sleep')
        self.assertEqual(fent[0]['status'], 'clean')

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
        ps = os.sep
        self.sandbox.add_file_content('file1', self.files[0])
        # destination not in repo
        self.assertRaises(PathInvalid,
                self.sandbox.rename, 'file1', join(pd, 'move1'))
        # invalid type for dest
        self.assertRaises(TypeError,
                self.sandbox.rename, 'file1', None)
        self.assertRaises(TypeError,
                self.sandbox.rename, 'file1', [join(pd, 'move1')])

        # can't overwrite file
        self.sandbox.add_file_content('move1', self.files[0])
        self.assertRaises(PathNotDir,
                self.sandbox.rename, ['file1'], 'move1')
        self.sandbox.add_file_content('file2', self.files[0])
        self.assertRaises(PathExists,
                self.sandbox.rename, ['file1', 'file2'], 'move1')
        self.assertRaises(PathInvalid,
                self.sandbox.rename, ['file1', 'file2'],
                join('move1', 'move2'))

        # no valid source
        ff, ss = self.sandbox.rename([ps + 'file1', ps + 'file2'], 'move2')
        self.assertEqual(len(ff), 0)
        self.assertEqual(len(ss), 0)

    def test_remove_file_str(self):
        for i, x in enumerate(self.filelist):
            self.sandbox.add_file_content(self.filelist[i], self.files[i])
        self.sandbox.remove(self.filelist[2])
        status = statdict(self.sandbox._repo.status(
                list_ignored=True, list_clean=True))
        self.assert_(self.filelist[2] not in status['added'])
        self.assert_(
            not os.path.exists(self.sandbox._fullpath(self.filelist[2])))
        self.sandbox.commit(self.msg, self.user)
        self.sandbox.remove(self.filelist[0])
        # private _repo
        status = statdict(self.sandbox._repo.status(
                list_ignored=True, list_clean=True))
        self.assertEqual(status['removed'], self.filelist[:1])

    def test_remove_file(self):
        for i, x in enumerate(self.filelist):
            self.sandbox.add_file_content(self.filelist[i], self.files[i])
        n1 = join('zzz', 'xxx', 'yyy', '111')
        self.sandbox.add_file_content(n1, 'nested file')
        self.sandbox.commit(self.msg, self.user)

        nested = [join('d', i) for i in self.filelist]
        for i, x in enumerate(self.filelist):
            self.sandbox.add_file_content(nested[i], self.files[i])

        # make one modified
        self.sandbox.add_file_content(self.filelist[0], 'wiped')

        clean = self.filelist[1:] + [n1]
        clean.sort()

        n2 = join('zzz', 'xxx', 'yyy', '222')
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

        # 1 modified, 2 clean, 1 added
        test1 = self.filelist + [n2]
        self.sandbox.remove(test1)

        # private _repo
        status = statdict(self.sandbox._repo.status(
                list_ignored=True, list_clean=True))

        self.assert_(not os.path.exists(self.sandbox._fullpath(n2)))
        self.assertEqual(status['removed'], self.filelist)

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
        status['removed'] = fl

    def test_rename_file_success(self):
        self.sandbox.add_file_content('file1', self.files[0])
        errs, copied = self.sandbox.rename('file1', 'move1')
        self.assertEqual(len(errs), 0)
        # private _repo
        status = statdict(self.sandbox._repo.status())
        self.assertEqual(copied[0], 'file1')
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
        self.assertEqual(status['removed'], [old_t])  # u not commited yet

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
        self.sandbox.add_file_content('file4', self.files[0])
        self.sandbox.commit(self.msg, self.user)
        errs, copied = self.sandbox.rename(['file1', 'file2', 'file3'], 'move1')
        self.assertEqual(len(errs), 0)
        self.assertEqual(len(copied), 3)

        # moving some back
        errs, copied = self.sandbox.rename(
            [
                join('move1', 'file1'),
                join('move1', 'file2'),
                join('move2', 'file3'),
            ],
            '',
        )
        self.assertEqual(len(errs), 0)  # error silently ignored
        self.assertEqual(len(copied), 2)

        # not there anymore
        errs, copied = self.sandbox.rename(
            [
                join('move1', 'file1'),
                join('move1', 'file3'),
            ],
            '',
        )
        self.assertEqual(copied, join(['move1/file3']))
        self.sandbox.add_file_content('move1/file1', self.files[0])
        self.sandbox.add_file_content('move1/file2', self.files[0])
        self.sandbox.remove('file3')
        errs, copied = self.sandbox.rename(['file1', 'file2', 'file3'], 'move1')
        # file3 is now invalid, no error
        # [move1/file1, move1/file2] both exists
        self.assertEqual(len(errs), 2)
        # alphabetical
        self.assertEqual(errs[0][0], 'file1')
        self.assertEqual(errs[1][0], 'file2')

def statdict(st):
    # build a stat dictionary
    changetypes = (
        'modified', 'added', 'removed', 'deleted', 'unknown', 
        'ignored', 'clean',
    )
    return dict(zip(changetypes, st))

def test_suite():
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(SandboxTestCase))
    suite.addTest(makeSuite(RepositorySandboxTestCase))
    suite.addTest(makeSuite(RepositoryTestCase))
    suite.addTest(makeSuite(RepositoryInitTestCase))
    return suite

if __name__ == '__main__':
    unittest.main()
