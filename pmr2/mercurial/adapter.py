import zope.interface
from zope.publisher.interfaces import NotFound, IPublisherRequest

from mercurial.hgweb import webcommands, webutil
from mercurial.hgweb.common import ErrorResponse
from mercurial import error

from pmr2.mercurial import WebStorage, Storage, Sandbox, utils
from pmr2.mercurial.interfaces import *
from pmr2.mercurial.exceptions import *
from pmr2.mercurial.utils import tmpl


class PMR2StorageAdapter(WebStorage):
    """\
    To adapt a PMR2 content object to a standard Storage object.

    It's up to subclasses of this class to register themselves as 
    adapters.
    """

    zope.interface.implements(IPMR2HgWorkspaceAdapter)

    def __init__(self, context, rev=None):
        """
        context -
            The object to turn into a workspace
        rev -
            The revision (optional)
        """

        self.context = context
        root = context.get_path()
        WebStorage.__init__(self, root, rev)


class PMR2StorageRequestAdapter(WebStorage):
    """\
    To adapt a PMR2 content object to a WebStorage object, as it is
    planned for use with a request.

    This adapter is more suited from within views.
    """

    zope.interface.implements(IPMR2HgWorkspaceAdapter)

    def __init__(self, context, request):
        """
        context -
            The object to turn into a workspace
        request -
            The request
        """

        # XXX we assume request has this
        self.context = context
        root = context.get_path()
        self.request = request
        self._rev = request.get('rev', None)
        self._path = '/'.join(request.get('request_subpath', ()))

        # build hgweb internal structures from the values we already
        # processed.
        if self._rev:
            request.form['node'] = [request.get('rev')]
        if self._path:
            request.form['file'] = ['/'.join(request.get('request_subpath'))]

        WebStorage.__init__(self, root, self._rev)

    @property
    def path(self):
        return self._path

    @property
    def short_rev(self):
        return utils.filter(self.rev, 'short')

    def get_manifest(self, path=None):
        """\
        Returns manifest at path.
        """

        result = WebStorage.manifest(self, self.request).next()
        return result

    _structure = WebStorage.structure

    @property
    def structure(self):
        """\
        Returns file or manifest at path.
        """

        # TODO? cache results?
        result = self._structure(self.request).next()
        return result

    @property
    def rawfile(self):
        """\
        Returns file or manifest at path.
        """

        req = self.request
        path = webutil.cleanpath(self.repo, req.form.get('file', [''])[0])
        if not path:
            raise PathNotFound("path '%s' not found" % path)
        try:
            fctx = webutil.filectx(self.repo, req)
        except error.LookupError, inst:
            raise
        path = fctx.path()
        text = fctx.data()
        #mt = mimetypes.guess_type(path)[0]
        #if mt is None:
        #    mt = binary(text) and 'application/octet-stream' or 'text/plain'
        return text

    def get_fileinfo(self, path=None):
        """\
        Returns file information at path.
        """

        result = WebStorage.fileinfo(self, self.rev, path).next()
        result['date'] = utils.filter(result['date'], 'isodate')
        return result

    def get_log(self, rev=None, branch=None, shortlog=False, datefmt=None, 
            maxchanges=None):
        """\
        Returns log.
        """

        if rev is None:
            rev = self.rev
        # XXX valid datefmt values might need to be documented/checked
        return self.log(rev, branch, shortlog, datefmt, maxchanges).next()
