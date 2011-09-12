import os
import re
import cgi
import ConfigParser
from cStringIO import StringIO
from mercurial import ui
from mercurial import hg
from mercurial import revlog
from mercurial import demandimport
from mercurial import cmdutil
from mercurial import scmutil
from mercurial import util
from mercurial import context
from mercurial.i18n import _

from mercurial.hgweb.hgweb_mod import hgweb, perms

# Mercurial exceptions to catch
from mercurial.error import RepoError, LookupError, LockHeld
from mercurial.util import Abort
from mercurial.hgweb.common import ErrorResponse, HTTP_NOT_FOUND
import mercurial.hgweb.protocol
from mercurial.hgweb.request import wsgirequest
from mercurial.hgweb import webcommands

from pmr2.app.workspace.exceptions import *

from pmr2.mercurial import utils, ext
from ext import hg_copy, hg_rename

demandimport.disable()

__all__ = [
    'Storage',
    'WebStorage',
    'FixedRevWebStorage',
    'Sandbox',
]

_t = utils.tmpl

class pmr2ui(ui.ui):
    """\
    Customizing the UI class to not write stuff out to stdout/stderr.
    """

    def __init__(self, src=None):
        ui.ui.__init__(self, src)
        self.ferr = self.fout = StringIO()
        self._errors = []
        if src:
            self._buffers = src._buffers
            self._errors = src._errors

    def write_err(self, *args, **kw):
        if self._errors:
            self._errors[-1].extend([str(a) for a in args])
        else:
            ui.ui.write_err(self, *args, **kw)

    def push_errors(self):
        self._errors.append([])

    def pop_errors(self):
        return self._errors.pop()


class _cwd:
    """ placeholder value for current working dir """


class Storage(object):
    """\ 
    Encapsulates a mercurial repository object.

    Provides methods to access and manipulate a mercurial repository.
    Based on mercurial.commands, but abstracted in a way that becomes a
    friendly software library that can be reused.

    This is a read only storage that borrows a lot of functionality from
    hgweb_mod.
    """

    def __init__(self, rpath, ctx=None):
        """\
        Creates the object wrapper for the repository object.

        This method only sets the repository path.

        `path' should be 'str', but 'unicode' is accepted but it will
        be encoded into a utf-8 encoded 'str' by default.
        """

        if isinstance(rpath, str):
            self._rpath = rpath
        elif isinstance(rpath, unicode):
            self._rpath = rpath.encode('utf8')
        else:
            raise TypeError('path must be an instance of basestring')
        
        u = pmr2ui()
        u.setconfig('ui', 'report_untrusted', 'off')
        u.setconfig('ui', 'interactive', 'off')
        u.readconfig(os.path.join(self._rpath, '.hg', 'hgrc'))

        self._ui = u
        try:
            self._repo = hg.repository(self._ui, self._rpath)
        except RepoError:
            # Repository initializing error.
            # XXX should include original traceback
            raise PathInvalidError('repository does not exist at path')

        if isinstance(ctx, unicode):
            ctx = ctx.encode('utf8')

        self._changectx(ctx)

    @staticmethod
    def create(path, create_dir=True, ffa=False):
        """\
        Creates a repository at the location that was specified during
        the creation of this repository object.

        `create_dir' specifies whether to create the directory for the
        hg repo if create is set to true.  Default: True

        `ffa' determines if a free for all access config file should be
        written.  Will create if True.  Default is False.
        """

        def write_ffa_access(path):
            config_path = os.path.join(path, '.hg', 'hgrc',)
            f = open(config_path, 'w')
            f.write(
                '[web]\n'
                'push_ssl = false\n'
                'allow_push = *\n'
            )
            f.close()

        if create_dir:
            if os.path.isdir(path):
                raise PathExistsError('directory already exist; '
                        'cannot create a new repository in existing directory')
            try:
                os.makedirs(path, mode=0700)
            except OSError:
                raise PathInvalidError('repository directory cannot be created')

        result = False
        try:
            u = pmr2ui()
            u.setconfig('ui', 'report_untrusted', 'off')
            u.setconfig('ui', 'interactive', 'off')
            if hg.repository(u, path, create=1):
                if ffa:
                    write_ffa_access(path)
                result = True
        except:
            # XXX should include original traceback
            # XXX assuming to be invalid path
            raise PathInvalidError("couldn't create repository at path")

        return result

    def _getctx(self, changeid=None):
        """\
        A private helper method that wraps around changectx of 
        mercurial repository; it will return the "default" branch as 
        according to dirlist.
        """

        # this is used because we are just going to present users with
        # the latest changes regardless for now.
        if changeid is None:
            changeid = 'tip'

        try:
            # it's possible to do self._repo[changeid]
            ctx = self._repo.changectx(changeid)
        except (RepoError, revlog.LookupError,):
            raise RevisionNotFoundError('revision %s not found' % changeid)
        return ctx

    def _changectx(self, changeid=None):
        """\
        same as above but changes the local ctx.
        """

        self._ctx = self._getctx(changeid)
        return self._ctx 

    def branches(self):
        return self._repo.branchtags()

    def clone(self, dest, rev=None, update=True):
        """\
        Clones this repository to target destination `dest'.

        dest -
            the destination.
        rev -
            specifies specific revisions to clone.
        """

        if not isinstance(dest, basestring):
            raise TypeError('dest must be an instance of basestring')

        if isinstance(dest, unicode):
            dest = dest.encode('utf8')

        dest = os.path.normpath(dest)

        if os.path.exists(dest):
            raise PathExistsError('dest already exists')

        pdir = os.path.split(dest)[0]
        if not os.path.exists(pdir):
            # try to create parent dir.
            try:
                os.makedirs(pdir, mode=0700)
            except:
                raise PathInvalidError(
                        'cannot create directory with specified path')

        if rev:
            try:
                rev = [self._repo.lookup(rev)]
            except:
                raise RevisionNotFoundError('revision %s not found' % rev)

        clone_result = hg.clone(self._ui, {}, source=self._rpath, dest=dest, 
                rev=rev, update=update)
        repo, repo_clone = clone_result
        # since it did get reinitialized.
        self._repo = repo

    def log(self, rev=None, branch=None, shortlog=False, 
            datefmt=None, maxchanges=None, *a, **kw):
        """\
        This method returns the history of the repository.

        rev -
            specifies which revision to start the history from.
        branch -
            specifies which branch to check the logs on.

        This method is implemented as a wrapper around hgweb.changelog(),
        so the value return is actually an iterator, and the structure
        will likely change when this class is migrated to a common
        interface.

        This method will not cause the internal context to change.
        """

        # XXX maybe move this into the hgweb_ext
        def changelist(entries, **x):
            for i in entries():
                i['date'] = getdate(i['date'])
                if shortlog:
                    i['desc'] = utils.filter(i['desc'], 'firstline')
                    i['author'] = utils.filter(i['author'], 'person')
                yield i

        hw = hgweb(self._repo)
        hw.refresh()

        if maxchanges is not None:
            hw.maxchanges = hw.maxshortchanges = maxchanges

        # This is kind of silly.
        if shortlog and datefmt is None:
            datefmt = 'age'
        elif datefmt is None:
            datefmt = 'isodate'

        getdate = lambda i: utils.filter(i, datefmt)

        # only looking, not changing.
        ctx = self._getctx(rev)
        result = ext.changelog(hw, ctx, _t, shortlog)
        for i in result:
            i['orig_entries'] = i['entries']
            i['entries'] = lambda **x: changelist(i['orig_entries'], **x)
            yield i

    def raw_manifest(self, rev=None):
        """\
        Returns raw manifest.

        Useful for grabing the list of entire files.
        """

        ctx = self._changectx(rev)
        return ctx.manifest()

    def _filectx(self, rev=None, path=None):
        """\
        Returns contents of file.
        """
        
        if not path:
            raise PathInvalidError('path unspecified')

        ctx = self._changectx(rev)
        try:
            return ctx.filectx(path)
        except revlog.LookupError:
            raise PathNotFoundError("path '%s' not found" % path)

    def file(self, rev=None, path=None):
        fctx = self._filectx(rev, path)
        return fctx.data()

    def fileinfo(self, rev=None, path=None):
        hw = hgweb(self._repo)
        fctx = self._filectx(rev, path)
        return webcommands._filerevision(hw, _t, fctx)

    def tags(self):
        return self._repo.tags()

    @property
    def rev(self):
        if self._ctx:
            return self._ctx.node().encode('hex')


class WebStorage(hgweb, Storage):
    """\
    Storage methods that are meant to be used by http requests are found
    in this class, with the revision locked.  As a result, the methods 
    in the parent class that has the revision argument have been removed.
    """

    def __init__(self, rpath, ctx=None):
        Storage.__init__(self, rpath, ctx)
        hgweb.__init__(self, self._repo)

    def structure(self, request, datefmt='isodate'):
        """\
        This method is implemented as a wrapper around webcommands.file
        and returns a structure.
        """

        # XXX deprecate this method?

        try:
            it = webcommands.file(self, request, _t)
            return utils.add_aentries(it, datefmt)
        except LookupError:
            if self.path:
                result = utils.match_subrepo(self.ctx.substate, self.path)
                if result:
                    return result
                raise PathNotFoundError("path '%s' not found" % self.path)
            else:
                raise RepoEmptyError('repository is empty')

    def process_request(self, request):
        """
        Process the request object and returns output.
        """

        protocol = mercurial.hgweb.protocol
        request.stdin.seek(0)
        env = dict(request.environ)
        headers_set = []
        headers_sent = []

        def write(data):
            if not headers_set:
                raise AssertionError("write() before start_response()")

            elif not headers_sent:
                # Before the first output, send the stored headers
                status, response_headers = headers_sent[:] = headers_set
                status, code = status.split(' ', 1)
                request.response.setStatus(status, code)
                for header in response_headers:
                    # let zope deal with the header.
                    request.response.setHeader(*header)

            out.write(data)
            out.flush()

        def start_response(status, response_headers, exc_info=None):
            if exc_info:
                try:
                    if headers_sent:
                        # Re-raise original exception if headers sent
                        raise exc_info[0], exc_info[1], exc_info[2]
                finally:
                    exc_info = None     # avoid dangling circular ref
            elif headers_set:
                raise AssertionError("Headers already set!")

            headers_set[:] = [status, response_headers]
            return write

        # XXX this is a hgweb object already.  While run_wsgi has what
        # we need, Zope/repoze/Plone handles some of the request stuff
        # already, so we just skip some of the parsing steps.

        out = StringIO()
        req = wsgirequest(env, start_response)

        self.refresh()

        req.url = req.env['SCRIPT_NAME']
        if not req.url.endswith('/'):
            req.url += '/'
        if 'REPO_NAME' in req.env:
            req.url += req.env['REPO_NAME'] + '/'

        if 'PATH_INFO' in req.env:
            parts = req.env['PATH_INFO'].strip('/').split('/')
            repo_parts = req.env.get('REPO_NAME', '').split('/')
            if parts[:len(repo_parts)] == repo_parts:
                parts = parts[len(repo_parts):]
            query = '/'.join(parts)
        else:
            query = req.env['QUERY_STRING'].split('&', 1)[0]
            query = query.split(';', 1)[0]

        # process this if it's a protocol request
        # protocol bits don't need to create any URLs
        # and the clients always use the old URL structure

        cmd = req.form.get('cmd', [''])[0]
        if cmd:
            if not protocol.iscmd(cmd):
                raise UnsupportedCommandError('%s is unsupported' % cmd)
            # XXX not sure why?
            #if query:
            #    raise ErrorResponse(HTTP_NOT_FOUND)
            try:
                if cmd in perms:
                    try:
                        self.check_perm(req, perms[cmd])
                    except ErrorResponse, inst:
                        if cmd == 'unbundle':
                            req.drain()
                        raise
                content = protocol.call(self.repo, req, cmd)
            except ErrorResponse, inst:
                req.respond(inst, protocol.HGTYPE)
                # XXX doing write here because the other methods expect
                # output.
                write('0\n')
                if not inst.message:
                    return []
                write('%s\n' % inst.message,)
                return out.getvalue()
            except KeyError, e:
                # XXX why can't Mercurial's exception be a bit more
                # consistent...
                raise ProtocolError()

        # XXX writing value out here because method expects it.
        for chunk in content:
            write(chunk)
        return out.getvalue()


class FixedRevWebStorage(WebStorage):
    """\
    WebStorage subclass that fixes revision.
    """

    def __init__(self, rpath, ctx):
        WebStorage.__init__(self, rpath, ctx)

    @property
    def ctx(self):
        return self._ctx

    @property
    def path(self):
        return self._path

    def raw_manifest(self):
        """\
        Returns raw manifest within the current context
        """

        return self.ctx.manifest()

    def _filectx(self, path=None):
        """\
        Returns contents of file within the current context.
        """

        if not path:
            if not hasattr(self, '_path'):
                # could use a better exception type/message.
                raise AttributeError('path is unknown')
            path = self._path

        try:
            return self.ctx.filectx(path)
        except revlog.LookupError:
            raise PathNotFoundError("path '%s' not found" % path)

    def file(self, path=None):
        fctx = self._filectx(path)
        return fctx.data()

    def fileinfo(self, path=None):
        fctx = self._filectx(path)
        return webcommands._filerevision(self, _t, fctx)


class Sandbox(Storage):
    """\
    This class implements features that is required by the PMR2 sandbox
    upload model.  Features provided allows manipulation of files,
    creation of changesets (commits).
    """

    def __init__(self, *a, **kw):
        Storage.__init__(self, *a, **kw)
        #self.t = _t
        #self.stripecount = 1
        #self.hgweb.status = _status

    def _getctx(self, changeid=None):
        """\
        Returns working context by default
        """
        # XXX attribute selection could use some work.

        if changeid is _cwd:
            ctx = context.workingctx(self._repo)
            return ctx
        else:
            return Storage._getctx(self, changeid)

    def _fullpath(self, name):
        """\
        validates and returns the name provided is within the context
        of this repository.

        all methods that need to create file need to call this first
        on the input name.
        """
        if os.path.isabs(name):
            fn = name
        else:
            fn = os.path.normpath(os.path.join(self._rpath, name))
        if not fn.startswith(self._rpath):
            raise PathInvalidError('supplied path is outside repository')
        return fn

    def _filter_paths(self, paths):
        # filter out paths using fullpath.
        # assumes files in manifest/status exist on filesystem

        def fullpath(name):
            try: return self._fullpath(name)
            except: return None

        # must resolve full path as cwd is almost always elsewhere.
        result = [fullpath(i) for i in paths]
        result = [i for i in result if i is not None and os.path.exists(i)]
        return result

    def _source_check(self, source):
        # param type check
        if isinstance(source, basestring):
            # XXX can this really work with unicode?  below also
            return [source]
        if not isinstance(source, list):
            raise TypeError(
                    'source must be either a list of strings or a string')
        for i in source:
            if not isinstance(i, basestring):
                raise TypeError('invalid type present in source list')
        return source

    def add(self, names):
        """\
        Selects a list of files to be added.

        Maybe break this one out?
        """
        fn = names
        if not isinstance(names, list):
            fn = [names]
        self._repo[None].add(fn)

    def add_file_content(self, name, content):
        """\
        This method adds content to the filename.
        """
        fn = self._fullpath(name)
        dirname = os.path.dirname(fn)
        if not os.path.isdir(dirname):
            # create the directory
            self.mkdir(dirname)
        fp = open(fn, 'wb')
        fp.write(content)
        fp.close()
        if not name in self._repo.dirstate:
            self._repo[None].add([name])

    def commit(self, message, user):
        """\
        Commits the changes made, returns the id of the new commit.
        """

        if not message:
            raise ValueError('message cannot be empty')
        if not user:
            raise ValueError('user cannot be empty')
        result = self._repo.commit(message, user, '')
        # remaining parmas: files, message, user, date, match function
        if result is not None:
            # we have new context
            self._changectx(result)
        return result

    def current_branch(self):
        return self._repo.dirstate.branch()

    def file(self, rev=_cwd, path=None):
        """
        Get the file in working directory using the working directory
        context.
        """

        fctx = self._filectx(rev, path)
        return fctx.data()

    def fileinfo(self, rev=_cwd, path=None):
        """
        Get the fileinfo in working directory using the working 
        directory context.
        """

        fctx = self._filectx(rev, path)
        if rev is _cwd and path not in fctx.manifest():
            raise PathNotFoundError("path '%s' not found" % path)
        hw = hgweb(self._repo)
        return ext.filerevision(hw, _t, fctx)

    def mkdir(self, dirname):
        """\
        Creates a dir with dirname.  Currently provided as helper.

        Normally there isn't a need to call this, as Mercurial does not
        track directories.  Adding a file to a specific location should
        create the directory if it does not already exist.
        """

        fn = self._fullpath(dirname)
        if not os.path.exists(fn):
            try:
                os.makedirs(fn, mode=0700)
            except:  # OSError:
                raise PathInvalidError(
                        'cannot create directory with specified path')
        elif not os.path.isdir(fn):
            raise PathExistsError('cannot create directory; '
                                    'path already exists')
        return True

    def pull(self, source='default', update=True):
        """\
        Pull new revisions from source.

        source -
            if value is 'default', the default source of this repo will 
            be used.

            Default: 'default'
        update -
            if True, this sandbox will be updated to the latest data
            that was pulled, if possible.

        return value is a number of total heads generated from the pull.

        0 = no changes
        1 = updated
        >1 = merge will be required, no automatic update
        """

        # not using another Storage because localrepo.addchangegroup
        # appends output to its ui, so the 'other' repo must be
        # created using the ui belonging to this object.
        if not isinstance(source, basestring):
            raise TypeError('source must be a string')
            # pull from main repo only.
        # XXX could implement pull up to specific revs
        repo = self._repo
        dest, branches = hg.parseurl(source)
        revs, checkout = hg.addbranchrevs(repo, repo, branches, [])
        if source == 'default':
            raise RepoNotFoundError('no suitable repository found')

        other = hg.repository(self._ui, source)
        self._ui.status('pulling from %s\n' % (source))
        modheads = self._repo.pull(other, revs)

        if update:
            if modheads <= 1 or checkout:
                hg.update(self._repo, checkout)
                self._changectx()
            else:
                self._ui.status(_("not updating, since new heads added\n"))

        return modheads

    def push(self, dest=None, rev=None, force=False):
        """\
        Push changes into destination.

        If destination is none, the source of this repo will be used.

        If revision is not specified, the current working dir will be
        pushed.  If this spawns a new head, this operation must be
        forced.

        Forcing will have the side effect of creating a new branch, and
        it may not be desirable.

        By default, no remote branch will be created.
        """

        # find parents
        # if there are two parents, take the first one,
        #   (ui should warn users about uncommitted merge/confirmation)
        # if not force, do it and see if head shows up

        if rev is None:
            rev = [self._repo.lookup('.')]

        dest = self._ui.expandpath(dest or 'default-push', 
                                   dest or 'default')
        repo = self._repo
        dest, branches = hg.parseurl(dest)
        revs, checkout = hg.addbranchrevs(repo, repo, branches, rev)

        if dest in ('default', 'default-push',):
            raise RepoNotFoundError('no suitable target found')
        other = hg.repository(self._ui, dest)
        self._ui.status('pushing to %s\n' % (dest))
        if revs:
            revs = [self._repo.lookup(rev) for rev in revs]
        try:
            r = self._repo.push(other, force, revs=revs)
        except Abort:
            raise ProtocolError()
        # check to see if this revision is present on destination
        # XXX assuming other is localrepo
        try:
            result = other.lookup(revs[0])
        except:
            result = None
        return result is not None

    def remove(self, source):
        """\
        This method removes files.

        source -
            the list of files to remove.  string or list of strings.
        """

        filtered = self._filter_paths(self._source_check(source))
        remove, forget = [], []

        m = scmutil.match(self._repo[None], filtered, {})
        s = self._repo.status(match=m, clean=True)
        modified, added, deleted, clean = s[0], s[1], s[3], s[6]
        # assume forced, and purge
        remove, forget = modified + deleted + clean + added, added
        for f in remove:
            try:
                util.unlinkpath(self._repo.wjoin(f))
            except OSError, inst:
                pass
        self._repo[None].forget(remove)

    def rename(self, source, dest, force=False):
        """\
        This method contains a copy of mercurial.commands.rename, used
        to rename source into dest.

        source -
            either a string of a list of strings that are valid paths.
            invalid paths will be silently ignored.
        dest -
            must be a string.

        There are two return values.
        First value is a list of tuples of files and the reason rename
        failed for it.  Invalid paths will not be here as they are 
        silently ignored.
        Second value is a list of files that were moved.
        """

        # param type check
        source = self._source_check(source)
        if not isinstance(dest, basestring):
            # XXX can this really work with unicode?  below also
            raise TypeError('dest must be of type string')

        # remove dupes
        origin = set(source)
        # source validation + param type check
        pats = self._filter_paths(origin)
        # destination.
        f_dest = self._fullpath(dest)

        c = len(pats)
        if c == 0:
            # no valid source, do nothing
            return [], []
        if c == 1:
            if os.path.exists(f_dest) and not os.path.isdir(f_dest):
                raise PathNotDirError(
                        'destination exists and is not a directory')
                # in UI, it could prompt the user that the dest file 
                # will be overwritten, and implement it as delete of 
                # dest and move from source to dest.
        else:
            # make path if source files > 1 as required by docopy
            self.mkdir(f_dest)

        pats.append(f_dest)  # add destination pattern list

        opts = {'force': force, 'after': 0}
        self._ui.push_errors()
        ec, success = hg_rename(self._ui, self._repo, *pats, **opts)
        errors = self._ui.pop_errors()
        errors.sort()
        return errors, success

    def status(self, path=''):
        """\
        Status reports the state of the sandbox, for files that may have
        been added, modified, deleted and the like.

        Only compare the first dirstate parent and working directory.

        Returns a dictionary of the list of files.
        """

        # get back to latest working copy because this is what we want.
        ctx = self._changectx(_cwd)
        st = self._repo.status(ignored=True, clean=True)

        hw = hgweb(self._repo)
        return ext.status(hw, _t, self._ctx, path, st)

# XXX features missing compared to prototype in pmr2.hgpmr.repository
# - archive: should be done via hgweb
# - tagging: should be done in sandbox (to create .hgtag)
# - merging: this must be done more comprehensively than prototype
# - forest snapshot: it was more a hack
