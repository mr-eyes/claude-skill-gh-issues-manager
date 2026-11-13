"""Where the plugin keeps its local files, and the checks that keep a planted file from being read.

The index and the hook state never live in the project tree, which a cloned
repository controls. They live in the plugin's data folder (CLAUDE_PLUGIN_DATA,
set by Claude Code), else in $XDG_CACHE_HOME/gh-issues-manager (index) and
$XDG_STATE_HOME/gh-issues-manager (state), by default ~/.cache and ~/.local/state.

Every folder the plugin uses there, from its top folder down, must be a real
folder (not a symlink), owned by the current user and not writable by group or
others; the plugin creates them with mode 0700. Files are written to a fresh
temporary file with mode 0600 and moved into place, and read without following
symlinks. A per-user key in the state folder lets the plugin recognize the
index files it created itself; an index without the right mark is not read.
"""

import hashlib
import hmac
import os
import stat
import tempfile

KEY_NAME = "key"


class StorageError(Exception):
    """A folder or file the plugin would use is not safe to use."""


def _env_dir(name, default):
    value = os.environ.get(name)
    return value if value and os.path.isabs(value) else default


def cache_root():
    data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if data and os.path.isabs(data):
        return data
    return os.path.join(_env_dir("XDG_CACHE_HOME", os.path.join(os.path.expanduser("~"), ".cache")), "gh-issues-manager")


def state_root(for_key=False):
    """The state folder. The key always lives under XDG_STATE_HOME, never in CLAUDE_PLUGIN_DATA."""
    data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if data and os.path.isabs(data) and not for_key:
        return data
    return os.path.join(_env_dir("XDG_STATE_HOME", os.path.join(os.path.expanduser("~"), ".local", "state")),
                        "gh-issues-manager")


def repo_folder(repo):
    name = repo.replace("/", "__")
    if not name or name.startswith(".") or "/" in name or "\\" in name:
        raise StorageError("unusable repository name %r" % repo)
    return name


def check_path(path, kind="folder"):
    """Raise StorageError unless `path` is a real folder or file, owned by this user, not writable by others."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(info.st_mode):
        raise StorageError("%s is a symlink; the plugin does not follow symlinks in its storage" % path)
    if kind == "folder" and not stat.S_ISDIR(info.st_mode) or kind == "file" and not stat.S_ISREG(info.st_mode):
        raise StorageError("%s is not a %s" % (path, kind))
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise StorageError("%s is not owned by the current user" % path)
    if info.st_mode & 0o022:
        raise StorageError("%s is writable by group or others (mode %o)" % (path, info.st_mode & 0o777))
    return True


def secure_folder(root, *parts):
    """Create root/parts with mode 0700 where missing and check every level from root down."""
    path = root
    for part in ("",) + parts:
        path = os.path.join(path, part) if part else path
        if not check_path(path):
            os.makedirs(path, mode=0o700, exist_ok=True)
            os.chmod(path, 0o700)
            check_path(path)
    return path


def read_file(path):
    """Text of a file read without following a symlink, or None when it does not exist."""
    if not check_path(path, "file"):
        return None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
        return handle.read()


def write_file(path, text):
    """Write through a fresh temporary file with mode 0600 in the same folder, then move it into place."""
    folder = os.path.dirname(path)
    check_path(folder)
    if os.path.lexists(path):
        check_path(path, "file")
    descriptor, temporary = tempfile.mkstemp(dir=folder, prefix=".part-")
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def user_key():
    """The per-user secret that marks index files this plugin created; made on first use."""
    folder = secure_folder(state_root(for_key=True))
    path = os.path.join(folder, KEY_NAME)
    text = read_file(path)
    if not text or len(text.strip()) < 32:
        write_file(path, os.urandom(32).hex() + "\n")
        text = read_file(path)
    return text.strip().encode("ascii")


def mark(path, repo):
    """The mark an index file of `repo` at `path` carries when this plugin, for this user, created it."""
    message = ("%s\n%s" % (os.path.abspath(path), repo.lower())).encode("utf-8")
    return hmac.new(user_key(), message, hashlib.sha256).hexdigest()
