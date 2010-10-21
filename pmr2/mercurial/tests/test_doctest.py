import unittest

from zope.testing import doctest
from Testing import ZopeTestCase as ztc

from pmr2.mercurial.tests import base

def test_suite():
    return unittest.TestSuite([

        ztc.ZopeDocFileSuite(
            'browser.txt', package='pmr2.mercurial',
            test_class=base.MercurialDocTestCase,
            optionflags=doctest.NORMALIZE_WHITESPACE|doctest.ELLIPSIS,
        ),

    ])

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
