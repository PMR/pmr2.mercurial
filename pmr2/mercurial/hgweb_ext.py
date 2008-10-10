import os.path

# needed for manifest/status method addon
from mercurial import util
from mercurial.context import filectx, workingfilectx
import mercurial.hgweb.hgweb_mod
from mercurial.hgweb.hgweb_mod import _up
from mercurial.hgweb.common import get_mtime, staticfile, style_map, paritygen

# not overriding builtin hex function like Mercurial does.
from binascii import hexlify

from mercurial import demandimport
demandimport.disable()

__all__ = [
    'hgweb_ext',
]

def hex_(data):
    if data is None:
        return ''  # XXX nullid prefered?
    else:
        return hexlify(data)


class hgweb_ext(mercurial.hgweb.hgweb_mod.hgweb):
    """\
    Customized hgweb_mod.hgweb class to include other vital methods
    required to generate usable output from other Mercurial features.
    """

    def status(self, tmpl, ctx, path, st):
        """\
        Based on hgweb.manifest, adapted to included features found in
        hg status.

        Initial parameters are the same as manifest.  New parameters:

        ctx
            - should be the workingctx
        st 
            - the tuple returned from repo.status
        """

        changetypes = (
            'modified', 'added', 'removed', 'deleted', 'unknown', 'ignored',
            'clean',
        )
        # status listing
        statlist = dict(zip(changetypes, st))
        filestatlist = {}
        for k, v in statlist.iteritems():
            for f in v:
                filestatlist[f] = k
        mf = ctx.manifest()
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
                fctx = ctx.filectx(full)
                yield {"file": full,
                       "status": filestatlist[full],
                       "parity": parity.next(),
                       "basename": f,
                       "date": fctx.changectx().date(),
                       "size": fctx.size(),
                       "permissions": mf.flags(full),
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

        return tmpl("status",
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

    def filecwd(self, tmpl, fctx):
        """\
        No change from Mercurial 1.0.2, except for usage of hexlify that
        can take `None` as input.
        """
        f = fctx.path()
        text = fctx.data()
        fl = fctx.filelog()
        n = fctx.filenode()
        parity = paritygen(self.stripecount)

        if util.binary(text):
            mt = mimetypes.guess_type(f)[0] or 'application/octet-stream'
            text = '(binary:%s)' % mt

        def lines():
            for lineno, t in enumerate(text.splitlines(1)):
                yield {"line": t,
                       "lineid": "l%d" % (lineno + 1),
                       "linenumber": "% 6d" % (lineno + 1),
                       "parity": parity.next()}

        return tmpl("filerevision",
                    file=f,
                    path=_up(f),
                    text=lines(),
                    rev=fctx.rev(),
                    node=hex_(fctx.node()),
                    author=fctx.user(),
                    date=fctx.date(),
                    desc=fctx.description(),
                    branch=self.nodebranchnodefault(fctx),
                    parent=self.siblings(fctx.parents()),
                    child=self.siblings(fctx.children()),
                    rename=self.renamelink(fl, n),
                    permissions=fctx.manifest().flags(f))

    def filerevision(self, tmpl, fctx):
        """\
        Same as one in mercurial 1.0.2, with a modification that allows
        passing in a working file context.
        """

        f = fctx.path()
        text = fctx.data()
        fl = fctx.filelog()
        n = fctx.filenode()
        parity = paritygen(self.stripecount)

        if util.binary(text):
            mt = mimetypes.guess_type(f)[0] or 'application/octet-stream'
            text = '(binary:%s)' % mt

        def lines():
            for lineno, t in enumerate(text.splitlines(1)):
                yield {"line": t,
                       "lineid": "l%d" % (lineno + 1),
                       "linenumber": "% 6d" % (lineno + 1),
                       "parity": parity.next()}

        # XXX might be better to override self.renamelink instead of
        # making this conditional statement here.
        # still need the hex_ method call.
        if isinstance(fctx, workingfilectx):
            return tmpl("filerevision",
                        file=f,
                        path=_up(f),
                        text=lines(),
                        rev=fctx.rev(),
                        node=hex_(fctx.node()),
                        author=fctx.user(),
                        date=fctx.date(),
                        desc=fctx.description(),
                        branch=self.nodebranchnodefault(fctx),
                        parent=self.siblings(fctx.parents()),
                        child=self.siblings(fctx.children()),
                        rename=[],  # XXX figure out how to derive this
                        permissions=fctx.manifest().flags(f))

        else:
            return tmpl("filerevision",
                        file=f,
                        path=_up(f),
                        text=lines(),
                        rev=fctx.rev(),
                        node=hex_(fctx.node()),
                        author=fctx.user(),
                        date=fctx.date(),
                        desc=fctx.description(),
                        branch=self.nodebranchnodefault(fctx),
                        parent=self.siblings(fctx.parents()),
                        child=self.siblings(fctx.children()),
                        rename=self.renamelink(fl, n),
                        permissions=fctx.manifest().flags(f))

