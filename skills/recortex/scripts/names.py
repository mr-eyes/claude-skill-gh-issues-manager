"""The plugin's names: the current ones, and the ones it had before it was renamed to recortex in version 0.5.0.

Every other module takes a name that changed from here, and reads the plugin's
environment variables only through env(). A name from before the rename is
read where the current one is absent, and nothing is moved or rewritten.

The comment markers `<!-- ghim:event ... -->` and `<!-- ghim:resume:start -->`
are not names in this sense: they are the record format, defined in
record_format.py and recortex.py, and they are not renamed, so that comments
posted before and after the rename are one format.

Standard library only, and nothing but `os`, so that storage.py can use it.
"""

import os

NAME = "recortex"
OLD_NAME = "gh-issues-manager"
CONFIG_NAME = ".recortex.json"
OLD_CONFIG_NAME = ".gh-issues-manager.json"
ENV_PREFIX = "RECORTEX_"
OLD_ENV_PREFIX = "GHIM_"
WORKFLOW = "recortex-triage.yml"
OLD_WORKFLOW = "ghim-triage.yml"
# The plugin's environment variables, without the prefix. The last three are read only by the tests.
VARIABLES = ("GH", "CONFIG", "TRUSTED_FILE", "TRUSTED_REPOS", "HOOK_TIMEOUT", "DISCOVERY", "SYNC_PAGE",
             "DATA_HOME", "TESTING", "TEST_KEEP")


def env(name, default=None):
    """RECORTEX_<name> when set to a non-empty value, else GHIM_<name> when non-empty, else default.

    A value of spaces is not empty, as in the shell's ${VAR:-default}, which run_hook.sh uses for the same rule.
    """
    for prefix in (ENV_PREFIX, OLD_ENV_PREFIX):
        value = os.environ.get(prefix + name)
        if value:
            return value
    return default


def env_source(name):
    """For --doctor: "new", "old", "both" or None, by which names of the variable are set to a non-empty value.
    It says which names are set, never a value."""
    new = bool(os.environ.get(ENV_PREFIX + name))
    old = bool(os.environ.get(OLD_ENV_PREFIX + name))
    if new and old:
        return "both"
    return "new" if new else "old" if old else None
