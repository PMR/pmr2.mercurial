# [hooks]
# pretxnchangegroup.01_one_head_per_branch = python:pmr2.mercurial.hooks.one_head_per_branch

def one_head_per_branch(ui, repo, **kwargs):
    for b in repo.branchtags():
        count = len(repo.branchheads(b))
        if count > 1:
            ui.warn(
                'trying to push more than one head to branch %s.\n'
                'please `hg pull` and then `hg merge` the outstanding heads.\n'
                'alternately, name your head as a new branch.\n' % b)
            return True
    return False
