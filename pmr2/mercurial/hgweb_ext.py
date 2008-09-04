import os.path

# needed for manifest/status method addon
import mercurial.hgweb.hgweb_mod
from mercurial.hgweb.hgweb_mod import _up
from mercurial.hgweb.common import get_mtime, staticfile, style_map, paritygen

# not overriding builtin hex function like Mercurial does.
from binascii import hexlify as hex_

__all__ = [
    'hgweb_ext',
]

class hgweb_ext(mercurial.hgweb.hgweb_mod.hgweb):
    """\
    Customized hgweb_mod.hgweb class to include other vital methods
    required to generate usable output from other Mercurial features.
    """

    def status(self, ctx, path, st):
        """\
        Based on hgweb.manifest, adapted to included features found in
        hg status.

        Initial parameters are the same as manifest.  New parameters:

        st 
            - the tuple returned from repo.status
        """

        changetypes = (
            'modified', 'added', 'removed', 'deleted', 'unknown', 'ignored',
            'clean',
        )
        # status listing
        statlist = dict(zip(changetypes, st))
        filelist = {}
        for k, v in statlist.iteritems():
            for f in v:
                filelist[f] = k

        # We only want the items present in filelist but not in the
        # manifest to be added to it (i.e. a non-overwriting update).
        # get the manifestdict object generated from ctx.manifest().
        mf_o = ctx.manifest()
        # We need a copy from the original manifest instead of generating
        # a new one from ctx.manifest() as that returns a reference to 
        # actual data that can be polluted when manipulated.
        mf = mf_o.copy()
        # update a standard dict with required dicts in the order needed
        # to generate the desired update dict.
        d = {}
        d.update(filelist)
        d.update(mf)
        # done.
        mf.update(d)

        node = ctx.node()

        files = {}
        parity = paritygen(self.stripecount)

        if path and path[-1] != "/":
            path += "/"
        l = len(path)
        abspath = "/" + path

        for f, n in mf.items():
            if f[:l] != path:
                continue
            remain = f[l:]
            if "/" in remain:
                short = remain[:remain.index("/") + 1] # bleah
                files[short] = (f, None)
            else:
                short = os.path.basename(remain)
                files[short] = (f, n)

        def filelist(**map):
            fl = files.keys()
            fl.sort()
            for f in fl:
                full, fnode = files[f]
                if not fnode:
                    continue
                # not only this, but it might be best to look for
                # 'clean' from statlist instead.
                if full in statlist['clean']:
                    fctx = ctx.filectx(full)
                    yield {"file": full,
                           "parity": parity.next(),
                           "basename": f,
                           "date": fctx.changectx().date(),
                           "size": fctx.size(),
                           "permissions": mf.flags(full),
                           }
                else:
                    yield {"file": full,
                           "parity": parity.next(),
                           "basename": f,
                           # XXX we need some real data for this
                           "date": (0, 0), #fctx.changectx().date(),
                           "size": 1, #fctx.size(),
                           "permissions": '', #mf.flags(full),
                           } 

        def dirlist(**map):
            fl = files.keys()
            fl.sort()
            for f in fl:
                full, fnode = files[f]
                if fnode:
                    continue

                yield {"parity": parity.next(),
                       "path": "%s%s" % (abspath, f),
                       "basename": f[:-1]}

        yield self.t("manifest",
                     rev=ctx.rev(),
                     node=hex_(node),
                     path=abspath,
                     up=_up(abspath),
                     upparity=parity.next(),
                     fentries=filelist,
                     dentries=dirlist,
                     archives=[], # self.archivelist(hex_(node)),
                     tags=self.nodetagsdict(node),
                     branches=self.nodebranchdict(ctx))
