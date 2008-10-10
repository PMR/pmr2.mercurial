class PathInvalid(ValueError):
    """path invalid"""


class PathNotDir(PathInvalid):
    """path not a directory"""


class PathNotFound(PathInvalid):
    """path not found"""


class PathExists(PathInvalid):
    """path exists"""


class RevisionNotFound(ValueError):
    """revision not found"""


class RepoEmpty(ValueError):
    """repository empty"""


class RepoNotFound(ValueError):
    """repository not found"""
