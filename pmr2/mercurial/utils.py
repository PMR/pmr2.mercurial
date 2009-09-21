import os
import os.path

from mercurial import archival, templatefilters
from pmr2.mercurial.exceptions import SubrepoPathUnsupportedError

_rstub = '.hg'

def webdir(path):
    """\
    Return a list of potentially valid repositores in `path`.
    """

    if not isinstance(path, str):
        raise TypeError('path must be a str')
    paths = os.listdir(path)
    result = [i for i in paths if os.path.isdir(os.path.join(path, i, _rstub))]
    return result

def filter(input, filter):
    """\
    Quick and dirty way to utilize the template filter to get dates.
    """

    try:
        return templatefilters.filters[filter](input)
    except:
        return input

def tmpl(name, **kw):
    kw[''] = name
    yield kw

def match_subrepo(substate, path):
    """
    Given a substate dict (like result of context.substate), match path,
    return a structure that describes what might be done.
    """

    # try to resolve submodule before giving up.
    for subrepokey, value in substate.iteritems():
        # appending separator is safe because hg considers
        # it as part of the subrepo.
        # XXX are subrepo path separator represented 
        # internally in hg as '/' under Windows, too?
        subrepodir = subrepokey + '/'
        # a request path with just the folder will be on its
        # own.
        if path == subrepokey or path.startswith(subrepodir):
            # sanity check, make sure link is redirectable.
            if not (value[0].startswith('http://') or
                    value[0].startswith('https://')
                ):  # <- sadface
                raise SubrepoPathUnsupportedError(
                    "subrepo path '%s' not supported" % value[0])
            # all good, produce subrepo info structure.
            newpath = path[len(subrepodir):]
            result = tmpl('_subrepo', **{
                'path': newpath,
                'location': value[0],
                'rev': value[1],
            })
            return result

file_listings = ['manifest']

def add_aentries(d, datefmt='isodate'):
    """\
    Process iterator returned by our custom template
    """

    d = d.next()

    if d[''] not in file_listings:
        return tmpl(d[''], **d)

    dirlist = d['dentries']
    filelist = d['fentries']

    def fulllist(**map):
        for i in dirlist():
            # remove first slash
            i['file'] = i['path'][1:]
            i['permissions'] = 'drwxr-xr-x'
            yield i
        for i in filelist():
            i['date'] = filter(i['date'], datefmt)
            i['permissions'] = filter(i['permissions'], 'permissions')
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

def archive(workspace, dest, node, kind, decode=True, matchfn=None,
            prefix=None, mtime=None):
    # assuming workspace is our workspace object
    repo = workspace._repo
    archival.archive(repo, dest, node, kind, decode, matchfn, prefix, mtime)
