import re
from os.path import basename
from cStringIO import StringIO

import zope.interface
from zope.publisher.interfaces import NotFound, IPublisherRequest

from mercurial.hgweb import webcommands, webutil
from mercurial.hgweb.common import ErrorResponse
from mercurial import error

from pmr2.mercurial import WebStorage, Storage, Sandbox, utils
from pmr2.mercurial.interfaces import *
from pmr2.mercurial.exceptions import *
from pmr2.mercurial.utils import tmpl, filter


class PMR2StorageAdapter(WebStorage):
    """\
    To adapt a PMR2 content object to a standard Storage object.

    It's up to subclasses of this class to register themselves as 
    adapters.
    """

    # XXX is it correct to imply that the revision cannot be respecified 
    # once this is instantiated?  Some method overrides below makes this
    # assumption, not all are.  This needs to be clarified.

    # Perhaps implement a raw storage class where free for all access is
    # enabled, with a locked down storage class that removes that access
    # be implemented?

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

    @property
    def _archive_name(self):
        reponame = re.sub(r"\W+", "-", basename(self._rpath))
        # skipping the part on deriving friendly branch names...
        arch_version = filter(self.rev, 'short')
        return "%s-%s" % (reponame, arch_version)

    def archive(self, type_, name=None):
        """\
        archive the repo.  based on webcommands.archive
        """

        if name is None:
            name = self._archive_name

        context = self.context
        rev = self.rev
        changectx = self._ctx

        # actual archive part
        out = StringIO()
        utils.archive(self, out, rev, type_, prefix=name)

        # we are done.
        return out.getvalue()

    def raw_manifest(self):
        """\
        override, locks down to this specific revision.
        """

        return self._ctx.manifest()


class PMR2StorageRequestAdapter(PMR2StorageAdapter):
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

        self.request = request
        self.parse_request()
        PMR2StorageAdapter.__init__(self, context, self._rev)

    @property
    def short_rev(self):
        return utils.filter(self.rev, 'short')

    # overriding structure,, since request is already provided.
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
            raise PathNotFoundError("path '%s' not found" % path)
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

    # overriding archive, since type is specified in the request.

    def archive(self):
        # this is the part that gets captured after the version info
        type_ = self.path
        name = self._archive_name
        # call parent to build the archive first.
        if type_ not in self.archives:
            raise KeyError('%s not a valid archive type', type_)
        mimetype, artype, extension, encoding = self.archive_specs[type_]
        result = PMR2StorageAdapter.archive(self, artype, name)

        # then build the headers for the response.
        headers = [
            ('Content-Type', mimetype),
            ('Content-Disposition', 'attachment; filename=%s%s' % (
                name, extension)),
        ]

        request = self.request
        if encoding:
            headers.append(('Content-Encoding', encoding))
        for header in headers:
            request.response.setHeader(*header)

        return result
