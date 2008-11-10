import os
import os.path

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
