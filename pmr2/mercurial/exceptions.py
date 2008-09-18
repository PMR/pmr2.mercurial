class PathInvalid(ValueError):
    """path invalid"""


class PathNotDir(PathInvalid):
    """path not a directory"""


class PathExists(PathInvalid):
    """path exists"""
