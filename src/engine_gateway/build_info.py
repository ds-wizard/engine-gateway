import collections

BuildInfo = collections.namedtuple(
    'BuildInfo',
    ['version', 'built_at', 'sha', 'branch', 'tag'],
)

BUILD_INFO = BuildInfo(
    version='unknown',
    built_at=None,
    sha=None,
    branch=None,
    tag='',
)
