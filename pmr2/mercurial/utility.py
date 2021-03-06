import re
from os.path import basename
from cStringIO import StringIO
import zope.component

from urlparse import parse_qsl
from mercurial.hgweb import webutil
from mercurial import archival

from pmr2.app.settings.interfaces import IPMR2GlobalSettings
from pmr2.app.workspace.exceptions import *
from pmr2.app.workspace.interfaces import IWorkspace
from pmr2.app.workspace.event import Push
from pmr2.app.workspace.storage import ProtocolResult
from pmr2.app.workspace.storage import StorageUtility
from pmr2.app.workspace.storage import BaseStorage

from pmr2.mercurial import backend
from pmr2.mercurial.utils import archive
from pmr2.mercurial.utils import filter
from pmr2.mercurial.utils import list_subrepo
from pmr2.mercurial.utils import match_subrepo


class MercurialStorageUtility(StorageUtility):
    title = u'Mercurial'
    command = u'hg'
    clone_verb = u'clone'

    def create(self, context):
        rp = zope.component.getUtility(IPMR2GlobalSettings).dirOf(context)
        # This creates the mercurial workspace, and will fail if storage
        # already exists.
        backend.Storage.create(rp, ffa=True)

    def acquireFrom(self, context):
        return MercurialStorage(context)

    # due to future extensions there may be cmd attributes that will
    # be sent by clients, so we can't prematurely filter protocol
    # like this:
    #
    # def isprotocol(self, request):
    #     return webutil.protocol.iscmd(request.get('cmd', None))
    #
    # So we do this:

    def isprotocol(self, request):
        result = request.get('cmd', None) is not None
        if not result:
            # workaround, as POST request somehow QUERY_STRING is not
            # parsed into request.form since Plone 4.1.
            qs = request.environ.get('QUERY_STRING', '')
            result = 'cmd=' in qs
        return result

    def protocol(self, context, request):
        storage = self.acquireFrom(context)
        # Assume WSGI compatible.
        raw_result = storage.storage.process_request(request)
        event = None
        if (request.method == 'POST' and
                dict(parse_qsl(request.environ.get('QUERY_STRING', ''))).get(
                    'cmd') == 'unbundle'):
            event = Push(context)
        return ProtocolResult(raw_result, event)

    def syncIdentifier(self, context, identifier):
        # method is not protected.
        rp = zope.component.getUtility(IPMR2GlobalSettings).dirOf(context)
        # use the sandbox class directly on the path
        sandbox = backend.Sandbox(rp)
        heads = sandbox.pull(identifier, update=False)
        msg = None
        result = heads > 0
        if heads == 0:
            msg = 'No new changes found.'
        # always successful, failure are exceptions
        return True, msg

    def syncWorkspace(self, context, source):
        remote = zope.component.getUtility(IPMR2GlobalSettings).dirOf(source)
        return self.syncIdentifier(context, remote)


class MercurialStorage(BaseStorage):

    # One of the future item is to modify this to more closely interact
    # with the mercurial library rather than go through one of our
    # previous abstractions.
    
    def __init__(self, context):
        rp = zope.component.getUtility(IPMR2GlobalSettings).dirOf(context)
        self.context = context

        # It may be better to merged WebStorage into this class (or the 
        # other way around) as this is really a wrapper around another
        # wrapper class.  For the mean time however, this does separate
        # what is known to be good from the part that interfaces with
        # pmr2.app.workspace.interfaces.IStorage.
        # 
        # Alternately, reimplement each of these methods based on what
        # is found inside mercurial.hgweb.*
        self.storage = backend.WebStorage(rp)

        # Default checkout value to set `self.rev`.
        self.checkout('tip')

    __datefmt_filter = {
        'rfc2822': 'rfc822date',
        'rfc3339': 'rfc3339date',
        'iso8601': 'isodate',
    }

    _archiveFormats = {
        'zip': ('Zip File', '.zip', 'application/zip',),
        'tgz': ('Tarball (gzipped)', '.tar.gz', 'application/x-tar',),
    }

    @property
    def datefmtfilter(self):
        return MercurialStorage.__datefmt_filter[self.datefmt]

    @property
    def rev(self):
        return self.__rev

    @property
    def shortrev(self):
        return filter(self.rev, 'short')

    def hg_archive(self, prefix, format):
        dest = StringIO()
        repo = self.storage.repo
        decode = True
        matchfn = None
        mtime = None
        archival.archive(repo, dest, self.rev, format,
                         decode, matchfn, prefix, mtime)
        return dest.getvalue()

    def archive_zip(self):
        arctype = 'zip'
        # could derive friendly branch name from rev to append on top
        # of revision id.
        reponame = re.sub(r"\W+", "-", basename(self.storage._rpath))
        name = "%s-%s" % (reponame, self.shortrev)
        return self.hg_archive(name, arctype)

    def archive_tgz(self):
        arctype = 'tgz'
        # could derive friendly branch name from rev to append on top
        # of revision id.
        reponame = re.sub(r"\W+", "-", basename(self.storage._rpath))
        name = "%s-%s" % (reponame, self.shortrev)
        return self.hg_archive(name, arctype)

    def basename(self, name):
        return name.split('/')[-1]

    def checkout(self, rev=None):
        ctx = self.storage._changectx(rev)
        self.__rev = ctx.node().encode('hex')

    # Unit tests would be useful here, even if this class will only
    # produce output for the browser classes.

    def file(self, path):
        # XXX see backend.Storage for why we need to pass self.rev and
        # why that should be unnecessary.
        return self.storage.file(self.rev, path)

    def fileinfo(self, path):
        data = self.storage.fileinfo(self.rev, path).next()
        ctx = self.storage._ctx
        fctx = ctx.filectx(data['file'])
        data['date'] = filter(data['date'], self.datefmtfilter)
        data['size'] = fctx.size()
        data['path'] = path  # we use full path here
        data['contents'] = lambda: self.file(data['file'])
        return self.format(**data)

    def files(self):
        return sorted(self.storage.raw_manifest(self.rev).keys())

    def listdir(self, path):
        """\
        Modification of the function
        mercurial.hgweb.webcommands.manifest
        """

        ctx = self.storage._ctx
        path = webutil.cleanpath(self.storage._repo, path)
        mf = ctx.manifest()
        node = ctx.node()
        substate = ctx.substate

        def fullviewpath(base, node, file):
            # XXX this needs to be some kind of resolution method
            view = 'file'
            return '%s/%s/%s/%s' % (base, view, node, file)

        if path in mf:
            raise PathNotDirError('path is dir: ' + path)

        files = {}
        dirs = {}
        subrepos = []

        if path and path[-1] != "/":
            path += "/"
        l = len(path)
        abspath = "/" + path

        for f, n in mf.iteritems():
            if f[:l] != path:
                continue
            remain = f[l:]
            elements = remain.split('/')
            if len(elements) == 1:
                files[remain] = f
            else:
                h = dirs # need to retain ref to dirs (root)
                for elem in elements[0:-1]:
                    if elem not in h:
                        h[elem] = {}
                    h = h[elem]
                    if len(h) > 1:
                        break
                h[None] = None # denotes files present

        if mf and not files and not dirs:
            raise PathNotFoundError('path not found: ' + path)

        subrepos = list_subrepo(substate, abspath)

        def listdir():

            if not path == '':
                yield self.format(**{
                    'permissions': 'drwxr-xr-x',
                    'contenttype': None,
                    'node': self.rev,
                    'date': '',
                    'size': '',
                    'path': '%s..' % path,
                    'desc': '',
                    'contents': '',  # XXX
                    # 'emptydirs': '/'.join(emptydirs),
                })
                
            for n, v in sorted(subrepos):
                p = ''
                url, rev, repotype = v
                if v[0] is None:
                    # can't really link it anywhere...
                    p = '%s%s' % (path, n)
                else:
                    # XXX 'file' is specific to PMR2, bitbucket uses
                    # 'src' to access the human friendly view.
                    p = '%s/file/%s' % (url, rev)
                result = self.format(**{
                    'permissions': 'lrwxrwxrwx',
                    'contenttype': repotype,
                    'node': self.rev,
                    'date': '',
                    'size': '',
                    'path': p,
                    'desc': '',
                    'contents': '',  # XXX
                    # 'emptydirs': '/'.join(emptydirs),
                })
                
                # need to "fix" some values
                result['basename'] = n  # name
                result['fullpath'] = p  # full url
                yield result

            for d in sorted(dirs):
                emptydirs = []
                h = dirs[d]
                while isinstance(h, dict) and len(h) == 1:
                    k, v = h.items()[0]
                    if v:
                        emptydirs.append(k)
                    h = v

                p = '%s%s' % (path, d)
                yield self.format(**{
                    'permissions': 'drwxr-xr-x',
                    'contenttype': 'folder',
                    'node': self.rev,
                    'date': '',
                    'size': '',
                    'path': p,
                    'desc': '',
                    'contents': '',  # XXX
                    # 'emptydirs': '/'.join(emptydirs),
                })

            for f in sorted(files):
                full = files[f]
                fctx = ctx.filectx(full)
                yield self.format(**{
                    'permissions': '-rw-r--r--',
                    'contenttype': 'file',
                    'node': self.rev,
                    'date': filter(fctx.date(), self.datefmtfilter),
                    'size': str(fctx.size()),
                    'path': full,
                    'desc': fctx.description(),
                    # XXX if self.rev changes, this can result in inconsistency
                    'contents': lambda: self.file(p),
                })

        return listdir()

    def pathinfo(self, path):

        if path in self.files():
            return self.fileinfo(path)

        try:
            listing = self.listdir(path)
            # consider using an iterator?
            contents = lambda: listing
            data = self.format(**{
                'permissions': 'drwxr-xr-x',
                'node': self.rev,
                'date': '',
                'size': '',
                'path': path,
                'contents': contents,
            })
        except PathNotFoundError:
            # attempt to look for subrepo
            ctx = self.storage._ctx
            substate = ctx.substate
            gen = match_subrepo(substate, path)
            if not gen:
                raise  # re-raise the PathNotFound
            keys = gen.next()
            # General syntax.
            data = self.format(**{
                'permissions': 'lrwxrwxrwx',
                'contenttype': None,  # XXX unnecessary for now
                'node': self.rev,
                'date': '',
                'size': '',
                'path': path,
                'desc': '',
                'contents': '',
                'external': keys,
            })
        return data

    def log(self, start, count, branch=None, shortlog=False):
        def buildnav(nav):
            # This is based on the navlist structure as expected by
            # pmr2.app.browser.page.NavPage
            # We have to merge Mercurial's before and after structure
            # together.
            result = []
            before = (callable(nav['before']) and nav['before']()
                or nav['before'])
            after = (callable(nav['after']) and nav['after']() or nav['after'])
            for i in before:
                result.append({
                    'href': i['node'],
                    'label': i['label'],
                })
            for i in after:
                result.append({
                    'href': i['node'],
                    'label': i['label'],
                })
            return result

        log = self.storage.log(rev=start, branch=branch, maxchanges=count,
                               shortlog=shortlog)
        results = log.next()
        changenav = results['changenav'][0]
        self._lastnav = buildnav(changenav)
        return results['entries']()
