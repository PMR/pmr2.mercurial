import zope.schema
import zope.interface


class IPMR2HgWorkspaceAdapter(zope.interface.Interface):
    """\
    Adapter class between PMR2 content class and pmr2.mercurial
    Workspace object
    """

    # XXX missing fields (such as rev)
    # XXX missing methods
