from os.path import dirname
from os.path import join

import zope.component

from plone.testing import Layer
from plone.testing.z2 import ZSERVER_FIXTURE
from plone.app.testing import IntegrationTesting
from plone.app.testing import FunctionalTesting
from plone.app.testing import PloneSandboxLayer
from plone.app.testing import PLONE_FIXTURE
from plone.app.testing import helpers

from pmr2.app.workspace.content import WorkspaceContainer
from pmr2.app.workspace.content import Workspace
from pmr2.app.workspace.tests.base import WorkspaceDocTestCase
from pmr2.app.exposure.tests.base import ExposureDocTestCase
from pmr2.app.settings.interfaces import IPMR2GlobalSettings

from pmr2.app.tests.layer import PMR2_FIXTURE
from pmr2.app.workspace.tests.layer import WORKSPACE_BASE_FIXTURE


class MercurialBaseLayer(PloneSandboxLayer):

    defaultBases = (PMR2_FIXTURE,)

    def setUpZope(self, app, configurationContext):
        import pmr2.mercurial
        self.loadZCML(package=pmr2.mercurial)

    def setUpPloneSite(self, portal):
        self.applyProfile(portal, 'pmr2.mercurial:default')

MERCURIAL_BASE_FIXTURE = MercurialBaseLayer()

MERCURIAL_BASE_INTEGRATION_LAYER = IntegrationTesting(
    bases=(MERCURIAL_BASE_FIXTURE,),
    name="pmr2.mercurial:basic_integration",
)


class MercurialLayer(PloneSandboxLayer):

    defaultBases = (MERCURIAL_BASE_FIXTURE, WORKSPACE_BASE_FIXTURE,)

    def setUpPloneSite(self, portal):
        import pmr2.mercurial.tests
        from pmr2.app.workspace.content import Workspace
        from pmr2.mercurial.tests import util

        settings = zope.component.getUtility(IPMR2GlobalSettings)

        p = settings.createDir(portal.workspace)
        util.extract_archive(p)

        def mkhg_workspace(name):
            w = Workspace(name)
            w.storage = u'mercurial'
            w.title = u''
            w.description = u''
            portal.workspace[name] = w

        mkhg_workspace('import1')
        mkhg_workspace('import2')
        mkhg_workspace('pmr2hgtest')
        mkhg_workspace('simple1')
        mkhg_workspace('simple2')
        mkhg_workspace('simple3')

MERCURIAL_FIXTURE = MercurialLayer()

MERCURIAL_INTEGRATION_LAYER = IntegrationTesting(
    bases=(MERCURIAL_FIXTURE,),
    name="pmr2.mercurial:integration",
)

MERCURIAL_LIVE_FUNCTIONAL_LAYER = FunctionalTesting(
    bases=(MERCURIAL_FIXTURE, ZSERVER_FIXTURE,),
    name="pmr2.mercurial:live_functional",
)
