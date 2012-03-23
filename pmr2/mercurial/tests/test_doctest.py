from unittest import TestCase, TestSuite, makeSuite
import doctest

from Testing import ZopeTestCase as ztc

from pmr2.mercurial.tests import base

def test_suite():
    browser = ztc.ZopeDocFileSuite(
        'browser.txt', package='pmr2.mercurial',
        test_class=base.MercurialDocTestCase,
        optionflags=doctest.NORMALIZE_WHITESPACE|doctest.ELLIPSIS,
    )
    synchronize = ztc.ZopeDocFileSuite(
        'synchronize.txt', package='pmr2.mercurial',
        test_class=base.MercurialDocTestCase,
        optionflags=doctest.NORMALIZE_WHITESPACE|doctest.ELLIPSIS,
    )
    synchronize.level = 9001
    return TestSuite([browser, synchronize])

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
