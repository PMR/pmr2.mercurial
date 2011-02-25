def mercurial(request):
    # standard Mercurial compatible client
    if 'HTTP_ACCEPT' in request.environ:
        return request.environ['HTTP_ACCEPT'].startswith(
            'application/mercurial-')
    # older Mercurial client
    agent = request.get_header('User-agent')
    if agent:
        return agent.startswith('mercurial/proto-')
    # nothing else to check, assume not Mercurial
    return False

