import os
import os.path

from mercurial import templatefilters

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
