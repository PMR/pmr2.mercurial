import os.path
import mimetypes

# needed for manifest/status method addon
from mercurial import util, cmdutil
from mercurial.util import binary
from mercurial import match as _match
from mercurial.cmdutil import expandpats, match
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
    'hex_',
    'hg_rename',
    'hg_copy',
    'changelog',
    'filerevision',
    'status',
]

def hex_(data):
    if data is None:
        return ''  # XXX nullid prefered?
    else:
        return hexlify(data)

# XXX modified commands.rename from mercurial 1.3
def hg_rename(ui, repo, *pats, **opts):
    wlock = repo.wlock(False)
    try:
        return hg_copy(ui, repo, pats, opts, rename=True)
    finally:
        wlock.release()

# XXX modified cmdutil.copy from mercurial 1.3
# changed to return a list of files moved.
def hg_copy(ui, repo, pats, opts, rename=False):
    # called with the repo lock held
    #
    # hgsep => pathname that uses "/" to separate directories
    # ossep => pathname that uses os.sep to separate directories
    cwd = repo.getcwd()
    targets = {}
    after = opts.get("after")
    dryrun = opts.get("dry_run")

    def walkpat(pat):
        srcs = []
        m = match(repo, [pat], opts, globbed=True)
        for abs in repo.walk(m):
            state = repo.dirstate[abs]
            rel = m.rel(abs)
            exact = m.exact(abs)
            if state in '?r':
                if exact and state == '?':
                    ui.warn(_('%s: not copying - file is not managed\n') % rel)
                if exact and state == 'r':
                    ui.warn(_('%s: not copying - file has been marked for'
                              ' remove\n') % rel)
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
            return

        # check for overwrites
        exists = os.path.exists(target)
        if not after and exists or after and state in 'mn':
            if not opts['force']:
                ui.warn(_('%s: not overwriting - file exists\n') %
                        reltarget)
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
                else:
                    ui.warn(_('%s: cannot copy - %s\n') %
                            (relsrc, inst.strerror))
                    return True # report a failure

        if ui.verbose or not exact:
            if rename:
                ui.status(_('moving %s to %s\n') % (relsrc, reltarget))
            else:
                ui.status(_('copying %s to %s\n') % (relsrc, reltarget))

        targets[abstarget] = abssrc

        # fix up dirstate
        origsrc = repo.dirstate.copied(abssrc) or abssrc
        if abstarget == origsrc: # copying back a copy?
            if state not in 'mn' and not dryrun:
                repo.dirstate.normallookup(abstarget)
        else:
            if repo.dirstate[origsrc] == 'a' and origsrc == abssrc:
                if not ui.quiet:
                    ui.warn(_("%s has not been committed yet, so no copy "
                              "data will be stored for %s.\n")
                            % (repo.pathto(origsrc, cwd), reltarget))
                if repo.dirstate[abstarget] in '?r' and not dryrun:
                    repo.add([abstarget])
            elif not dryrun:
                repo.copy(origsrc, abstarget)

        if rename and not dryrun:
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
        if _match.patkind(pat):
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


    pats = expandpats(pats)
    if not pats:
        raise util.Abort(_('no source or destination specified'))
    if len(pats) == 1:
        raise util.Abort(_('no destination specified'))
    dest = pats.pop()
    destdirexists = os.path.isdir(dest) and not os.path.islink(dest)
    if not destdirexists:
        if len(pats) > 1 or _match.patkind(pats[0]):
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

    errors = 0
    success = []
    for targetpath, srcs in copylist:
        for abssrc, relsrc, exact in srcs:
            if copyfile(abssrc, relsrc, targetpath(abssrc), exact):
                errors += 1
            else:
                success.append(abssrc)

    #if errors:
    #    ui.warn(_('(consider using --after)\n'))

    return errors, success


# XXX copied from webcommands.changelog, hg v1.3, with the request part
# stripped out.
def changelog(web, ctx, tmpl, shortlog = False):
    def changelist(limit=0, **map):
        l = [] # build a list in forward order for efficiency
        for i in xrange(start, end):
            ctx = web.repo[i]
            n = ctx.node()
            showtags = webutil.showtag(web.repo, tmpl, 'changelogtag', n)
            files = webutil.listfilediffs(tmpl, ctx.files(), n, web.maxfiles)

            l.insert(0, {"parity": parity.next(),
                         "author": ctx.user(),
                         "parent": webutil.parents(ctx, i - 1),
                         "child": webutil.children(ctx, i + 1),
                         "changelogtag": showtags,
                         "desc": ctx.description(),
                         "date": ctx.date(),
                         "files": files,
                         "rev": i,
                         "node": hex_(n),
                         "tags": webutil.nodetagsdict(web.repo, n),
                         "inbranch": webutil.nodeinbranch(web.repo, ctx),
                         "branches": webutil.nodebranchdict(web.repo, ctx)
                        })

        if limit > 0:
            l = l[:limit]

        for e in l:
            yield e

    maxchanges = shortlog and web.maxshortchanges or web.maxchanges
    cl = web.repo.changelog
    count = len(cl)
    pos = ctx.rev()
    start = max(0, pos - maxchanges + 1)
    end = min(count, start + maxchanges)
    pos = end - 1
    parity = paritygen(web.stripecount, offset=start-end)

    changenav = webutil.revnavgen(pos, maxchanges, count, web.repo.changectx)

    return tmpl(shortlog and 'shortlog' or 'changelog',
                changenav=changenav,
                node=hex_(ctx.node()),
                rev=pos, changesets=count,
                entries=lambda **x: changelist(limit=0,**x),
                latestentry=lambda **x: changelist(limit=1,**x),
                archives=web.archivelist("tip"))

# XXX copied from mercurial 1.3
# modified hex to our hex_
def filerevision(web, tmpl, fctx):
    f = fctx.path()
    text = fctx.data()
    parity = paritygen(web.stripecount)

    if binary(text):
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
                branch=webutil.nodebranchnodefault(fctx),
                parent=webutil.parents(fctx),
                child=webutil.children(fctx),
                rename=webutil.renamelink(fctx),
                permissions=fctx.manifest().flags(f))

def status(web, tmpl, ctx, path, st, datefmt='isodate'):
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
    parity = paritygen(web.stripecount)

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
                 archives=[], # web.archivelist(hex_(node)),
                 tags=webutil.nodetagsdict(web.repo, ctx),
                 branches=webutil.nodebranchdict(web.repo, ctx))
