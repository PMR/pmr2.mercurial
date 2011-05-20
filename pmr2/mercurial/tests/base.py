from os.path import dirname
from os.path import join

import zope.component
from zope.component import testing
from Testing import ZopeTestCase as ztc
from Products.Five import zcml
from Products.Five import fiveconfigure
from Products.PloneTestCase import PloneTestCase as ptc
from Products.PloneTestCase.layer import PloneSite
from Products.PloneTestCase.layer import onsetup
from Products.PloneTestCase.layer import onteardown

import pmr2.testing
from pmr2.app.workspace.content import WorkspaceContainer
from pmr2.app.workspace.content import Workspace
from pmr2.app.workspace.tests.base import WorkspaceDocTestCase
from pmr2.app.exposure.tests.base import ExposureDocTestCase


@onsetup
def setup():
    import pmr2.app
    fiveconfigure.debug_mode = True
    zcml.load_config('configure.zcml', pmr2.mercurial)
    fiveconfigure.debug_mode = False
    ztc.installPackage('pmr2.app')

@onteardown
def teardown():
    pass

setup()
teardown()
# XXX dependant on pmr2.app still
ptc.setupPloneSite(products=('pmr2.app',))


class MercurialDocTestCase(ExposureDocTestCase):

    def setUp(self):
        # create real Hg repos, to be called only after workspace is
        # created and model root path is assigned
        super(MercurialDocTestCase, self).setUp()

        import pmr2.mercurial.tests
        from pmr2.app.workspace.content import Workspace
        from pmr2.mercurial.tests import util

        p = self.pmr2.createDir(self.portal.workspace)
        util.extract_archive(p)

        p2a_test = join(dirname(pmr2.testing.__file__), 'pmr2.app.testdata.tgz')
        util.extract_archive(p, p2a_test)

        self.pmr2hgtest_revs = util.ARCHIVE_REVS
        self.rdfmodel_revs = [
            'b94d1701154be42acf63ee6b4bd4a99d09ba043c',
            '2647d4389da6345c26d168bbb831f6512322d4f9',
            '006f11cd9211abd2a879df0f6c7f27b9844a8ff2',
        ]

        def mkhg_workspace(name):
            # XXX temporary method to work with existing tests until
            # this is replaced
            w = Workspace(name)
            w.storage = u'mercurial'
            w.title = u''
            w.description = u''
            self.portal.workspace[name] = w

        mkhg_workspace('import1')
        mkhg_workspace('import2')
        mkhg_workspace('pmr2hgtest')
        mkhg_workspace('rdfmodel')
