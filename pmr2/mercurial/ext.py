import os.path
import mimetypes

# needed for manifest/status method addon
from mercurial import util, cmdutil
from mercurial.context import filectx, workingfilectx
from mercurial.i18n import _
import mercurial.hgweb.hgweb_mod
from mercurial.hgweb import webcommands
from mercurial.hgweb import webutil
from mercurial.hgweb.common import get_mtime, staticfile, paritygen

# not overriding builtin hex function like Mercurial does.
from binascii import hexlify

from mercurial import demandimport
demandimport.disable()

from pmr2.mercurial import utils

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

    # XXX deprecated, do not use.
    # TODO move methods into custom webcommands module.

    def __init__(self, *a, **kw):
        super(hgweb_ext, self).__init__(*a, **kw)
        self.refresh()

    def status(self, tmpl, ctx, path, st, datefmt='isodate'):
        """\
        Based on hgweb.manifest, adapted to included features found in
        hg status.

        Initial parameters are the same as manifest.  New parameters:

        ctx
            - should be the workingctx
        st 
            - the tuple returned from repo.status
        datefmt
            - the date format of the full filelist.
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

        def fulllist(**map):
            for i in dirlist():
                # remove first slash
                i['file'] = i['path'][1:]
                i['permissions'] = 'drwxr-xr-x'
                yield i
            for i in filelist():
                i['date'] = utils.filter(i['date'], datefmt)
                i['permissions'] = utils.filter(i['permissions'], 'permissions')
                yield i

        return tmpl("status",
                     rev=ctx.rev(),
                     node=hex_(node),
                     path=abspath,
                     up=webutil.up(abspath),
                     upparity=parity.next(),
                     fentries=filelist,
                     dentries=dirlist,
                     aentries=fulllist,
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
                    path=webutil.up(f),
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
                        path=webutil.up(f),
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
                        path=webutil.up(f),
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

    def manifest(self, tmpl, ctx, path, datefmt='isodate'):

        d = webcommands.manifest(self, tmpl, ctx)
        d = d.next()

        dirlist = d['dentries']
        filelist = d['fentries']

        def fulllist(**map):
            for i in dirlist():
                # remove first slash
                i['file'] = i['path'][1:]
                i['permissions'] = 'drwxr-xr-x'
                yield i
            for i in filelist():
                i['date'] = utils.filter(i['date'], datefmt)
                i['permissions'] = utils.filter(i['permissions'], 'permissions')
                yield i

        return tmpl(d[''],
                    rev=d['rev'],
                    node=d['node'],
                    path=d['path'],
                    up=d['up'],
                    upparity=d['upparity'],
                    fentries=d['fentries'],
                    dentries=d['dentries'],
                    aentries=lambda **x: fulllist(**x),
                    archives=d['archives'],
                    tags=d['tags'],
                    inbranch=d['inbranch'],
                    branches=d['branches'],
                   )


# XXX modified commands.rename from mercurial 1.0.2
def hg_rename(ui, repo, *pats, **opts):
    wlock = repo.wlock(False)
    try:
        return hg_copy(ui, repo, pats, opts, rename=True)
    finally:
        del wlock

# XXX modified cmdutil.copy from mercurial 1.0.2
# changes to return a list of files moved.

def hg_copy(ui, repo, pats, opts, rename=False):
    # called with the repo lock held
    #
    # hgsep => pathname that uses "/" to separate directories
    # ossep => pathname that uses os.sep to separate directories
    cwd = repo.getcwd()
    targets = {}
    after = opts.get("after")
    dryrun = opts.get("dry_run")
    errormsg = []

    def walkpat(pat):
        srcs = []
        for tag, abs, rel, exact in cmdutil.walk(repo, [pat], opts, globbed=True):
            state = repo.dirstate[abs]
            if state in '?r':
                if exact and state == '?':
                    ui.warn(_('%s: not copying - file is not managed\n') % rel)
                    errormsg.append((abs, 
                            'not copying - file is not managed',))
                if exact and state == 'r':
                    ui.warn(_('%s: not copying - file has been marked for'
                              ' remove\n') % rel)
                    errormsg.append((abs, 
                            'not copying - file has been marked for remove',))
                continue
            # abs: hgsep
            # rel: ossep
            srcs.append((abs, rel, exact))
        return srcs

    # abssrc: hgsep
    # relsrc: ossep
    # otarget: ossep
    def copyfile(abssrc, relsrc, otarget, exact):
        abstarget = util.canonpath(repo.root, cwd, otarget)
        reltarget = repo.pathto(abstarget, cwd)
        target = repo.wjoin(abstarget)
        src = repo.wjoin(abssrc)
        state = repo.dirstate[abstarget]

        # check for collisions
        prevsrc = targets.get(abstarget)
        if prevsrc is not None:
            ui.warn(_('%s: not overwriting - %s collides with %s\n') %
                    (reltarget, repo.pathto(abssrc, cwd),
                     repo.pathto(prevsrc, cwd)))
            # XXX need to provide meaningful error message, find out what
            # prevsrc looks like
            errormsg.append((abssrc, '',))
            return

        # check for overwrites
        exists = os.path.exists(target)
        if (not after and exists or after and state in 'mn'):
            if not opts['force']:
                ui.warn(_('%s: not overwriting - file exists\n') %
                        reltarget)
                errormsg.append((abssrc, 'destination exists',))
                return

        if after:
            if not exists:
                return
        elif not dryrun:
            try:
                if exists:
                    os.unlink(target)
                targetdir = os.path.dirname(target) or '.'
                if not os.path.isdir(targetdir):
                    os.makedirs(targetdir)
                util.copyfile(src, target)
            except IOError, inst:
                if inst.errno == errno.ENOENT:
                    ui.warn(_('%s: deleted in working copy\n') % relsrc)
                    errormsg.append((abssrc, 'deleted in working copy',))
                else:
                    ui.warn(_('%s: cannot copy - %s\n') %
                            (relsrc, inst.strerror))
                    errormsg.append((abssrc, 'cannot copy - %s' % inst.strerror,))
                    return True # report a failure

        if ui.verbose or not exact:
            action = rename and "moving" or "copying"
            ui.status(_('%s %s to %s\n') % (action, relsrc, reltarget))

        targets[abstarget] = abssrc

        # fix up dirstate
        origsrc = repo.dirstate.copied(abssrc) or abssrc
        if abstarget == origsrc: # copying back a copy?
            if state not in 'mn' and not dryrun:
                repo.dirstate.normallookup(abstarget)
        else:
            if repo.dirstate[origsrc] == 'a':
                if not ui.quiet:
                    ui.warn(_("%s has not been committed yet, so no copy "
                              "data will be stored for %s.\n")
                            % (repo.pathto(origsrc, cwd), reltarget))
                if abstarget not in repo.dirstate and not dryrun:
                    repo.add([abstarget])
            elif not dryrun:
                repo.copy(origsrc, abstarget)

        if rename and not dryrun:
            #import pdb;pdb.set_trace()
            repo.remove([abssrc], not after)

    # pat: ossep
    # dest ossep
    # srcs: list of (hgsep, hgsep, ossep, bool)
    # return: function that takes hgsep and returns ossep
    def targetpathfn(pat, dest, srcs):
        if os.path.isdir(pat):
            abspfx = util.canonpath(repo.root, cwd, pat)
            abspfx = util.localpath(abspfx)
            if destdirexists:
                striplen = len(os.path.split(abspfx)[0])
            else:
                striplen = len(abspfx)
            if striplen:
                striplen += len(os.sep)
            res = lambda p: os.path.join(dest, util.localpath(p)[striplen:])
        elif destdirexists:
            res = lambda p: os.path.join(dest,
                                         os.path.basename(util.localpath(p)))
        else:
            res = lambda p: dest
        return res

    # pat: ossep
    # dest ossep
    # srcs: list of (hgsep, hgsep, ossep, bool)
    # return: function that takes hgsep and returns ossep
    def targetpathafterfn(pat, dest, srcs):
        if util.patkind(pat, None)[0]:
            # a mercurial pattern
            res = lambda p: os.path.join(dest,
                                         os.path.basename(util.localpath(p)))
        else:
            abspfx = util.canonpath(repo.root, cwd, pat)
            if len(abspfx) < len(srcs[0][0]):
                # A directory. Either the target path contains the last
                # component of the source path or it does not.
                def evalpath(striplen):
                    score = 0
                    for s in srcs:
                        t = os.path.join(dest, util.localpath(s[0])[striplen:])
                        if os.path.exists(t):
                            score += 1
                    return score

                abspfx = util.localpath(abspfx)
                striplen = len(abspfx)
                if striplen:
                    striplen += len(os.sep)
                if os.path.isdir(os.path.join(dest, os.path.split(abspfx)[1])):
                    score = evalpath(striplen)
                    striplen1 = len(os.path.split(abspfx)[0])
                    if striplen1:
                        striplen1 += len(os.sep)
                    if evalpath(striplen1) > score:
                        striplen = striplen1
                res = lambda p: os.path.join(dest,
                                             util.localpath(p)[striplen:])
            else:
                # a file
                if destdirexists:
                    res = lambda p: os.path.join(dest,
                                        os.path.basename(util.localpath(p)))
                else:
                    res = lambda p: dest
        return res


    pats = util.expand_glob(pats)
    if not pats:
        raise util.Abort(_('no source or destination specified'))
    if len(pats) == 1:
        raise util.Abort(_('no destination specified'))
    dest = pats.pop()
    destdirexists = os.path.isdir(dest) and not os.path.islink(dest)
    if not destdirexists:
        if len(pats) > 1 or util.patkind(pats[0], None)[0]:
            raise util.Abort(_('with multiple sources, destination must be an '
                               'existing directory'))
        if util.endswithsep(dest):
            raise util.Abort(_('destination %s is not a directory') % dest)

    tfn = targetpathfn
    if after:
        tfn = targetpathafterfn
    copylist = []
    for pat in pats:
        srcs = walkpat(pat)
        if not srcs:
            continue
        copylist.append((tfn(pat, dest, srcs), srcs))
    if not copylist:
        raise util.Abort(_('no files to copy'))

    success = []
    errors = 0
    for targetpath, srcs in copylist:
        for abssrc, relsrc, exact in srcs:
            if copyfile(abssrc, relsrc, targetpath(abssrc), exact):
                errors += 1
            else:
                success.append(abssrc)

    # this is only reported if IOError happened.
    #if errors:
    #    ui.warn(_('(consider using --after)\n'))

    return errormsg, success

