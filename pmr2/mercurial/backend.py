import os
import cgi
import ConfigParser
from cStringIO import StringIO
from mercurial import ui, hg, revlog, demandimport, cmdutil, util, context
from mercurial.i18n import _

from mercurial.hgweb.hgweb_mod import hgweb

# Mercurial exceptions to catch
from mercurial.error import RepoError, LookupError, LockHeld
from mercurial.util import Abort
from mercurial.hgweb.common import ErrorResponse
import mercurial.hgweb.protocol
from mercurial.hgweb.request import wsgirequest
from mercurial.hgweb import webcommands

from pmr2.mercurial.exceptions import *
from pmr2.mercurial import utils, ext
from ext import hg_copy, hg_rename

demandimport.disable()

__all__ = [
    'Storage',
    'Sandbox',
]

_t = utils.tmpl

class pmr2ui(ui.ui):
    """\
    Customizing the UI class to not write stuff out to stdout/stderr.
    """

    def __init__(self, src=None):
        ui.ui.__init__(self, src)
        self._errors = []
        if src:
            self._buffers = src._buffers
            self._errors = src._errors

    def write_err(self, *args):
        if self._errors:
            self._errors[-1].extend([str(a) for a in args])
        else:
            self.write(*args)

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
        u.pushbuffer()
        u.readconfig(os.path.join(self._rpath, '.hg', 'hgrc'))

        self._ui = u
        try:
            self._repo = hg.repository(self._ui, self._rpath)
        except RepoError:
            # Repository initializing error.
            # XXX should include original traceback
            raise PathInvalid('repository does not exist at path')

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
                raise PathExists('directory already exist; '
                        'cannot create a new repository in existing directory')
            try:
                os.makedirs(path, mode=0700)
            except OSError:
                raise PathInvalid('repository directory cannot be created')

        result = False
        try:
            u = pmr2ui()
            u.setconfig('ui', 'report_untrusted', 'off')
            u.setconfig('ui', 'interactive', 'off')
            u.pushbuffer()
            if hg.repository(u, path, create=1):
                if ffa:
                    write_ffa_access(path)
                result = True
        except:
            # XXX should include original traceback
            # XXX assuming to be invalid path
            raise PathInvalid("couldn't create repository at path")

        return result

    def _changectx(self, changeid=None):
        """\
        A private helper method that wraps around changectx of 
        mercurial repository; it will pick the "default" branch as 
        according to dirlist.
        """

        # this is used because we are just going to present users with
        # the latest changes regardless for now.
        if changeid is None:
            changeid = 'tip'

        try:
            self._ctx = self._repo.changectx(changeid)
        except (RepoError, revlog.LookupError,):
            raise RevisionNotFound('revision %s not found' % changeid)
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
            raise PathExists('dest already exists')

        pdir = os.path.split(dest)[0]
        if not os.path.exists(pdir):
            # try to create parent dir.
            try:
                os.makedirs(pdir, mode=0700)
            except:
                raise PathInvalid(
                        'cannot create directory with specified path')

        if rev:
            try:
                rev = [self._repo.lookup(rev)]
            except:
                raise RevisionNotFound('revision %s not found' % rev)

        clone_result = hg.clone(self._ui, source=self._rpath, dest=dest, 
                rev=rev, update=update)
        repo, repo_clone = clone_result
        # since it did get reinitialized.
        self._repo = repo

    def log(self, rev=None, branch=None, shortlog=False, 
            datefmt=None, maxchanges=None):
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
        """

        # maybe move this into the hgweb_ext
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

        if datefmt == 'age':
            getdate = lambda i: utils.filter(i, datefmt) + ' ago'
        else:
            getdate = lambda i: utils.filter(i, datefmt)

        ctx = self._changectx(rev)
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
            raise PathNotFound('path not found')

        ctx = self._changectx(rev)
        try:
            return ctx.filectx(path)
        except revlog.LookupError:
            raise PathNotFound("path '%s' not found" % path)

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
    def output(self):
        """\
        Returns raw outout generated by the backend.
        """
        result = self._ui.popbuffer()
        # reset the status messages.
        self._ui.pushbuffer()
        return result

    @property
    def rev(self):
        if self._ctx:
            return self._ctx.node().encode('hex')


class WebStorage(hgweb, Storage):
    """\
    Storage methods that are meant to be used by http requests are found
    in this class.
    """

    def __init__(self, rpath, ctx=None):
        Storage.__init__(self, rpath, ctx)
        hgweb.__init__(self, self._repo)

    def structure(self, request, datefmt='isodate'):
        """\
        This method is implemented as a wrapper around webcommands.file
        and returns a structure.
        """

        try:
            it = webcommands.file(self, request, _t)
            return utils.add_aentries(it, datefmt)
        except LookupError:
            if not request.form.get('file', []):
                raise RepoEmpty('repository is empty')
            else:
                raise PathNotFound("path '%s' not found" % path)

    def process_request(self, request):
        """
        Process the request object and returns output.
        """

        # XXX this will need to be rewritten to be more WSGI friendly.

        if request.REQUEST_METHOD != 'GET':
            # We need to do our own parsing, ZPublisher ignores POST.
            # This line will be a problem if Mercurial decides to do
            # POST properly (i.e. not use QUERY_STRING).
            items = cgi.parse_qsl(request.QUERY_STRING)
            request.form.update(dict(items))

        command = 'cmd' in request and request['cmd'] or None

        if not command:
            raise UnsupportedCommand('unspecified command')
        try:
            method = getattr(mercurial.hgweb.protocol, command)
        except AttributeError:
            raise UnsupportedCommand('%s is unsupported' % command)

        # we are in, so get back to the start
        request.stdin.seek(0)

        # XXX the request object *should* be WSGI compliant as Mercurial
        # supports it, but we are going to emulate it for now.
        env = dict(request.environ)
        # 'REQUEST_URI' is missing but seems to be unused
        env['REMOTE_HOST'] = env['REMOTE_ADDR']

        # emulate wsgi environment
        env['wsgi.version'] = (1, 0)
        # environment variable has https
        env['wsgi.url_scheme'] = request.base.split(':')[0]  # self.url_scheme
        env['wsgi.input'] = request.stdin # self.rfile
        env['wsgi.errors'] = StringIO() #_error_logger(self)
        env['wsgi.multithread'] = True  # XXX guess
        env['wsgi.multiprocess'] = True  # same as above
        env['wsgi.run_once'] = True

        # build hgweb object.
        hw = hgweb(self._repo)
        hw.close_connection = True
        hw.saved_status = None
        hw.saved_headers = []
        hw.sent_headers = False
        hw.length = None

        headers_set = []
        headers_sent = []

        # copied from mercurial.hgweb.wsgicgi, which in turn is copied
        # from PEP-0333 
        # http://www.python.org/dev/peps/pep-0333/#the-server-gateway-side

        out = StringIO()

        def write(data):
            if not headers_set:
                raise AssertionError("write() before start_response()")

            elif not headers_sent:
                # Before the first output, send the stored headers
                status, response_headers = headers_sent[:] = headers_set
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

        # prepare the environment, run it, return result manually.
        env = wsgirequest(env, start_response)
        method(hw, env)
        return out.getvalue()


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

    def _changectx(self, changeid=None):
        """\
        Returns working context by default
        """
        # XXX attribute selection could use some work.

        if changeid is _cwd:
            self._ctx = context.workingctx(self._repo)
            return self._ctx
        else:
            return Storage._changectx(self, changeid)

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
            raise PathInvalid('supplied path is outside repository')
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
        self._repo.add(fn)

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
            self._repo.add([name])

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
            raise PathNotFound("path '%s' not found" % path)
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
                raise PathInvalid(
                        'cannot create directory with specified path')
        elif not os.path.isdir(fn):
            raise PathExists('cannot create directory; '
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
        source, revs, checkout = hg.parseurl(source, [])
        if source == 'default':
            raise RepoNotFound('no suitable repository found')

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

        dest, revs, checkout = hg.parseurl(
            self._ui.expandpath(dest or 'default-push', 
                                dest or 'default'), rev)

        if dest in ('default', 'default-push',):
            raise RepoNotFound('no suitable target found')
        other = hg.repository(self._ui, dest)
        self._ui.status('pushing to %s\n' % (dest))
        if revs:
            revs = [self._repo.lookup(rev) for rev in revs]
        r = self._repo.push(other, force, revs=revs)
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

        m = cmdutil.match(self._repo, filtered, {})
        s = self._repo.status(match=m, clean=True)
        modified, added, deleted, clean = s[0], s[1], s[3], s[6]
        # assume forced, and purge
        remove, forget = modified + deleted + clean + added, added
        self._repo.forget(forget)
        self._repo.remove(remove, unlink=True)

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
                raise PathNotDir(
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
