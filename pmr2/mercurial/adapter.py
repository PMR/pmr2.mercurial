import re
from gzip import GzipFile
import tarfile
from os.path import basename, dirname
from cStringIO import StringIO

import zope.interface
from Acquisition import aq_parent, aq_inner

from mercurial.hgweb import webcommands, webutil
from mercurial.hgweb.common import ErrorResponse
from mercurial import error

from pmr2.mercurial import FixedRevWebStorage, WebStorage, Storage, Sandbox
from pmr2.mercurial.interfaces import *
from pmr2.mercurial.exceptions import *
from pmr2.mercurial.utils import archive, tmpl, filter


class PMR2StorageAdapter(WebStorage):
    """\
    To adapt a PMR2 content object to a WebStorage object.
    """

    zope.interface.implements(IPMR2HgWorkspaceAdapter)

    def __init__(self, context):
        """
        context -
            The object to turn into a workspace
        """

        self.context = context
        root = context.get_path()
        WebStorage.__init__(self, root)


class PMR2StorageFixedRevAdapter(FixedRevWebStorage):
    """\
    This adapter requires a fixed revision.
    """

    zope.interface.implements(IPMR2HgWorkspaceAdapter)

    def __init__(self, context, rev):
        self.context = context
        root = context.get_path()
        WebStorage.__init__(self, root, rev)

    @property
    def _archive_name(self):
        reponame = re.sub(r"\W+", "-", basename(self._rpath))
        # skipping the part on deriving friendly branch names...
        arch_version = filter(self.rev, 'short')
        return "%s-%s" % (reponame, arch_version)

    def _archive(self, artype, name):
        """\
        archive the repo.  based on webcommands.archive
        """

        context = self.context
        rev = self.rev
        changectx = self.ctx

        dest = StringIO()
        archive(self, dest, rev, artype, prefix=name)
        return dest

    def archive(self, artype, name=None, subrepo=False):
        if name is None:
            name = self._archive_name

        if (subrepo and self.ctx.substate) or (artype in ('tar', 'tgz')):
            result = self._archive_tar(name, subrepo, artype)
        else:
            # this is the core of what this method is supposed to do.
            result = self._archive(artype, name)

        return result

    def _archive_tar(self, name, subrepo=True, artype='tar'):
        """\
        This archives the subrepos.
        """

        substate = {}
        if subrepo:
            # check for subrepos (substates)
            substate = self.ctx.substate
        archives = []

        if not artype in ('tar', 'tgz'):
            raise KeyError('%s not supported for subrepo', artype)

        # generate archives of the stuff within.
        for location, subrepo in substate.iteritems():
            source, rev = subrepo
            if dirname(source) == dirname(self.context.absolute_url()):
                # Current we only support workspaces linked within 
                # the same folder.  Later maybe we can fix this to 
                # support other workspaces elsewhere on the site.

                # we can attempt to resolve the workspace object.
                wid = basename(source)
                folder = aq_parent(self.context)
                o = folder[wid]

                swp = zope.component.queryMultiAdapter((o, rev,), 
                    name="PMR2StorageFixedRev")
                # XXX assuming unix
                subname = '%s/%s' % (name, location)
                archives.append(swp._archive_tar(subname))
            else:
                # XXX we need to raise some sort of stink, maybe
                # deferr an exception till later.
                pass

        # we are only taring this up, will compress later.
        out = self._archive('tar', name)
        out.seek(0)

        tf = tarfile.open(name, 'a:', out)
        # join subarchives together.
        for a in archives:
            a.seek(0)
            tfa = tarfile.open('import', 'r', a)
            for i in tfa.getmembers():
                tf.addfile(i, tfa.extractfile(i))
            tfa.close()
            a.close()
        tf.close()
        out.seek(0)

        # only support gzip for now, standard tar otherwise.
        if artype == 'tgz':
            result = StringIO()
            # XXX hint for Fail^WWinzip because it does not speak 
            # mimetype and needs filename ext as hints to what to do.
            gz = GzipFile(name + '.tar', 'wb', fileobj=result)
            gz.write(out.getvalue())
            gz.close()
        else:
            result = out

        return result


class PMR2StorageRequestAdapter(PMR2StorageFixedRevAdapter):
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
        PMR2StorageFixedRevAdapter.__init__(self, context, self._rev)

    @property
    def short_rev(self):
        return filter(self.rev, 'short')

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
        result['date'] = filter(result['date'], 'isodate')
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

    def archive(self, subrepo=False):
        """\
        Extends upon the PMR2StorageAdapter class to be able to archive
        subrepos.
        """

        type_ = self.path
        name = self._archive_name
        mimetype, artype, extension, encoding = self.archive_specs[type_]
        # this is the core of what this method is supposed to do.
        result = PMR2StorageFixedRevAdapter.archive(
            self, artype, name, subrepo)

        # XXX check for type_ in archive_specs

        # The extension provided by this class is to build headers, 
        # since request is involved.
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
