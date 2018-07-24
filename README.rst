UNMAINTANED PACKAGE
===================

This package is no longer in use or maintained for the mean time.

Introduction
============

``pmr.mercurial`` provides a wrapper API around some of the internal
methods provided by the ``mercurial`` package, and the Mercurial storage
backend for the Physiome Model Repository (PMR).  Thus, this package is
intended to be used in conjunction with the `PMR Software Suite`_.

.. _PMR software suite: https://github.com/PMR/pmr2.buildout/

Installation
------------

By default, this package is included in the ``buildout.cfg`` within the
``pmr2.buildout`` package, which provides the instructions and scripts
for the installation of the complete PMR Software Suite.

While not recommended, you may manually install this package onto any
Zope/Plone installation by modifying the ``buildout.cfg`` to include
this package at the relevant locations, for example::

    [buildout]
    ...

    [instance]
    ...

    eggs =
        ...
        pmr2.mercurial

    zcml =
        ...
        pmr2.mercurial

Also, the find-links attribute need to include the download location
of the tarball for this package.

Usage
-----

For further usage information, please refer to the tests and the
associated text files within.
