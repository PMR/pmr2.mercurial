import re
from os.path import basename
from cStringIO import StringIO
import zope.component

from mercurial.hgweb import webutil
from mercurial import archival

from pmr2.app.settings.interfaces import IPMR2GlobalSettings
from pmr2.app.workspace.exceptions import *
from pmr2.app.workspace.interfaces import IWorkspace
from pmr2.app.workspace.storage import StorageUtility
from pmr2.app.workspace.storage import BaseStorage

from pmr2.mercurial import backend
from pmr2.mercurial.utils import archive
from pmr2.mercurial.utils import filter


class MercurialStorageUtility(StorageUtility):
    title = 'Mercurial'

    def create(self, context):
        rp = zope.component.getUtility(IPMR2GlobalSettings).dirOf(context)
        # This creates the mercurial workspace, and will fail if storage
        # already exists.
        backend.Storage.create(rp, ffa=True)

    def acquireFrom(self, context):
        return MercurialStorage(context)

    def protocol(self, context, request):
        storage = self.acquireFrom(context)
        try:
            return storage.storage.process_request(request)
        except AttributeError:
            # XXX need better/more elegant way to handle non-WSGI 
            # compatible objects.
            return


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

        if path in mf:
            raise PathNotDirError('path is dir: ' + path)

        files = {}
        dirs = {}

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

        def listdir():
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
                    'node': self.rev,
                    'date': '',
                    'size': '',
                    'path': p,
                    'contents': '',  # XXX
                    # 'emptydirs': '/'.join(emptydirs),
                })

            for f in sorted(files):
                full = files[f]
                fctx = ctx.filectx(full)
                yield self.format(**{
                    'permissions': '-rw-r--r--',
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
            data = self.fileinfo(path)
        else:
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
        return data

    def log(self, start, count, branch=None):
        log = self.storage.log(rev=start, branch=branch, maxchanges=count)
        return log.next()['entries']()
