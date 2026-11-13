"""Where the plugin keeps its local files, and the checks that keep a planted file from being read.

The index and the hook state never live in the project tree, which a cloned
repository controls. They live under a top folder: the plugin's data folder
(CLAUDE_PLUGIN_DATA, set by Claude Code), else $XDG_CACHE_HOME/gh-issues-manager
(index) and $XDG_STATE_HOME/gh-issues-manager (state and key), by default under
~/.cache and ~/.local/state.

Inside the top folder the plugin keeps everything in a private folder it creates
and controls, `private/`, with mode 0700:

- top folder: a real folder (not a symlink), owned by the user or by root. Claude
  Code creates CLAUDE_PLUGIN_DATA with the user's umask, so on a system with
  umask 0002 it is group-writable; when the user owns it, the plugin tightens it
  to 0700 and goes on. A top folder owned by another user, or by root and
  writable by others, is refused.
- private/ and everything below it: real folders and files owned by the user,
  with no permissions for group or others (folders 0700, files 0600), checked at
  every read and write.

Files are written to a fresh temporary file with mode 0600 and moved into place,
and read without following symlinks. A per-user key in the state folder lets the
plugin recognize the index files it created; an index without the right mark is
not read, so a swapped folder or a forged index is refused.
"""

import hashlib
import hmac
import os
import stat
import tempfile

PRIVATE = "private"
KEY_NAME = "key"


class StorageError(Exception):
    """A folder or file the plugin would use is not safe to use."""


def _env_dir(name, default):
    value = os.environ.get(name)
    return value if value and os.path.isabs(value) else default


def cache_top():
    data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if data and os.path.isabs(data):
        return data
    return os.path.join(_env_dir("XDG_CACHE_HOME", os.path.join(os.path.expanduser("~"), ".cache")), "gh-issues-manager")


def state_top(for_key=False):
    """The top folder for state. The key always lives under XDG_STATE_HOME, never in CLAUDE_PLUGIN_DATA."""
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


def _uid():
    return os.getuid() if hasattr(os, "getuid") else None


def check_top(path, create=True, tighten=True):
    """Check the top folder, tightening it to 0700 when the user owns it. False when it is missing and create is False.

    With tighten=False (for --doctor) a loose top folder owned by the user is accepted as it is and left unchanged.
    """
    parent = os.path.dirname(os.path.abspath(path))
    try:
        above = os.stat(parent)
        if above.st_mode & stat.S_IWOTH and not above.st_mode & stat.S_ISVTX:
            raise StorageError("%s is in %s, which anyone can write to without the sticky bit" % (path, parent))
    except FileNotFoundError:
        pass
    if not os.path.lexists(path):
        if not create:
            return False
        os.makedirs(path, mode=0o700, exist_ok=True)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        if os.path.islink(path):
            raise StorageError("%s is a symlink; the plugin does not follow symlinks in its storage" % path)
        raise StorageError("%s is not a folder the plugin can open" % path)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode):
            raise StorageError("%s is not a folder" % path)
        uid = _uid()
        if uid is None or info.st_uid == uid:
            if info.st_mode & 0o077 and tighten:
                # created with a loose umask; the user owns it, so tighten it, through the open descriptor
                if hasattr(os, "fchmod"):
                    os.fchmod(descriptor, 0o700)
                else:
                    os.chmod(path, 0o700)
        elif info.st_uid == 0:
            if info.st_mode & 0o022:
                raise StorageError("%s is owned by root and writable by others" % path)
        else:
            raise StorageError("%s is owned by another user" % path)
    finally:
        os.close(descriptor)
    return True


def check_path(path, kind="folder"):
    """Check a private folder or file: real, owned by the user, no permissions for group or others.

    Returns False when it does not exist; raises StorageError when it is not safe.
    """
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(info.st_mode):
        raise StorageError("%s is a symlink; the plugin does not follow symlinks in its storage" % path)
    if kind == "folder" and not stat.S_ISDIR(info.st_mode) or kind == "file" and not stat.S_ISREG(info.st_mode):
        raise StorageError("%s is not a %s" % (path, kind))
    uid = _uid()
    if uid is not None and info.st_uid != uid:
        raise StorageError("%s is not owned by the current user" % path)
    if info.st_mode & 0o077:
        raise StorageError("%s has permissions for group or others (mode %o); the plugin keeps it private. Run: "
                           "chmod %s %s" % (path, info.st_mode & 0o777, "700" if kind == "folder" else "600", path))
    return True


def folder(top, *parts, create=True, tighten=True):
    """top/private/parts, created with mode 0700 where missing and checked at every level. None when missing."""
    if not check_top(top, create, tighten):
        return None
    path = top
    for part in (PRIVATE,) + parts:
        path = os.path.join(path, part)
        if not check_path(path):
            if not create:
                return None
            os.makedirs(path, mode=0o700, exist_ok=True)
            os.chmod(path, 0o700)
            check_path(path)
    return path


def read_file(path):
    """Text of a private file read without following a symlink, or None when it does not exist."""
    if not check_path(path, "file"):
        return None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
        return handle.read()


def write_file(path, text):
    """Write through a fresh temporary file with mode 0600 in the same private folder, then move it into place."""
    target_folder = os.path.dirname(path)
    check_path(target_folder)
    if os.path.lexists(path):
        check_path(path, "file")
    descriptor, temporary = tempfile.mkstemp(dir=target_folder, prefix=".part-")
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


def key_path():
    return os.path.join(state_top(for_key=True), PRIVATE, KEY_NAME)


def user_key(create=True, tighten=True):
    """The per-user secret that marks index files this plugin created; made on first use."""
    private = folder(state_top(for_key=True), create=create, tighten=tighten)
    if private is None:
        raise StorageError("no key yet at %s" % key_path())
    path = os.path.join(private, KEY_NAME)
    text = read_file(path)
    if text is None:
        if not create:
            raise StorageError("no key yet at %s" % path)
        try:  # exclusive creation: of two first uses at the same moment, one writes and both read the same key
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, "w", encoding="ascii") as handle:
                handle.write(os.urandom(32).hex() + "\n")
        text = read_file(path)
    key = (text or "").strip()
    if len(key) < 32 or not all(c in "0123456789abcdef" for c in key):
        raise StorageError("the key at %s is damaged; the plugin does not replace it on its own. Move it away by "
                           "hand, and the indexes made with it will be rebuilt" % path)
    return key.encode("ascii")


def same_file(path, before):
    """True when `path` is still the regular file (device and inode) that `before` describes."""
    try:
        now = os.lstat(path)
    except FileNotFoundError:
        return False
    return stat.S_ISREG(now.st_mode) and (now.st_dev, now.st_ino) == (before.st_dev, before.st_ino)


def lstat_file(path):
    return os.lstat(path)


def mark(path, repo, create=True, tighten=True):
    """The mark an index file of `repo` at `path` carries when this plugin, for this user, created it."""
    message = ("%s\n%s" % (os.path.abspath(path), repo.lower())).encode("utf-8")
    return hmac.new(user_key(create, tighten), message, hashlib.sha256).hexdigest()


def describe(path):
    """For --doctor: (exists, owner, mode, problem or "") of a path, never raising and never reading contents."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return False, "", "", "missing"
    except OSError as error:
        return False, "", "", str(error)
    try:
        import pwd
        owner = pwd.getpwuid(info.st_uid).pw_name
    except (ImportError, KeyError):
        owner = str(info.st_uid)
    problem = ""
    if stat.S_ISLNK(info.st_mode):
        problem = "symlink"
    elif _uid() is not None and info.st_uid not in (_uid(), 0):
        problem = "owned by another user"
    return True, owner, "%o" % (info.st_mode & 0o7777), problem
