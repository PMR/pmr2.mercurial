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
