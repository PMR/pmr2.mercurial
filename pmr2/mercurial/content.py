import zope.schema
import zope.interface
import zope.component
from zope.publisher.interfaces import NotFound, IPublisherRequest

from pmr2.mercurial import Storage, Sandbox, utils
from pmr2.mercurial.interfaces import *
from pmr2.mercurial.exceptions import *


class PMR2StorageAdapter(Storage):
    """\
    To adapt a PMR2 content object to a Storage object.

    It's up to subclasses of this class to register themselves as 
    adapters.
    """

    zope.interface.implements(IPMR2HgWorkspaceAdapter)
    zope.component.adapts(IPMR2StorageBase)

    def __init__(self, context):
        """
        context -
            The object to turn into a workspace
        request -
            The request
        """

        self.context = context
        root = context.get_path()
        Storage.__init__(self, root)


class PMR2StorageRequestAdapter(PMR2StorageAdapter):
    """\
    To adapt a PMR2 content object to a Storage object.

    This adapter is more suited from within views.
    """

    zope.interface.implements(IPMR2HgWorkspaceAdapter)
    zope.component.adapts(IPMR2StorageBase, IPublisherRequest)

    def __init__(self, context, request):
        """
        context -
            The object to turn into a workspace
        request -
            The request
        """

        # XXX we assume request has this
        self.request = request
        self._rev = request.get('rev', None)
        self._path = '/'.join(request.get('request_subpath', ()))

        # similiar to parent
        self.context = context
        root = context.get_path()

        # however we have a specific revision, try this
        Storage.__init__(self, root, self._rev)

    @property
    def rev(self):
        return self._rev

    @property
    def path(self):
        return self._path

    def get_full_manifest(self):
        """\
        Returns full manifest listing.
        """

        return Storage.raw_manifest(self, self._rev)

    def get_manifest(self, path=None):
        """\
        Returns manifest at path.
        """

        if path is None:
            path = self.path
        result = Storage.manifest(self, self.rev, path).next()
        return result

    def get_fileinfo(self, path=None):
        """\
        Returns file information at path.
        """

        if path is None:
            path = self.path
        result = Storage.fileinfo(self, self.rev, path).next()
        result['date'] = utils.filter(result['date'], 'isodate')
        return result

    def get_log(self, rev=None, branch=None, shortlog=False, datefmt=None):
        """See IExposure"""

        # XXX valid datefmt values might need to be documented/checked
        storage = self.get_storage()
        return storage.log(rev, branch, shortlog, datefmt).next()

    @property
    def file(self):
        """\
        Returns content at path.
        """

        return Storage.file(self, self._rev, self._path)

    @property
    def fileinfo(self):
        """\
        Returns content at path.
        """

        if not hasattr(self, '_fileinfo'):
            try:
                self._fileinfo = self.get_fileinfo()
            except PathNotFound:
                self._fileinfo = None
        return self._fileinfo

    @property
    def manifest(self):
        """\
        Returns content at path.
        """

        if not hasattr(self, '_manifest'):
            try:
                self._manifest = self.get_manifest()
            except PathNotFound:
                self._manifest = None
        return self._manifest

