from unittest import TestCase, TestSuite, makeSuite
import doctest

from plone.testing import layered
from Testing import ZopeTestCase as ztc

from pmr2.mercurial.tests import base
from pmr2.mercurial.tests import layer


def test_suite():
    browser = ztc.ZopeDocFileSuite(
        'browser.txt', package='pmr2.mercurial',
        test_class=base.MercurialDocTestCase,
        optionflags=doctest.NORMALIZE_WHITESPACE|doctest.ELLIPSIS,
    )
    synchronize = layered(ztc.ZopeDocFileSuite(
            'synchronize.txt', package='pmr2.mercurial',
            test_class=ztc.FunctionalTestCase,
            optionflags=doctest.NORMALIZE_WHITESPACE|doctest.ELLIPSIS,
        ),
        layer=layer.MERCURIAL_LIVE_FUNCTIONAL_LAYER
    )
    return TestSuite([browser, synchronize])

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
