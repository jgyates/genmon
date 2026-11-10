#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: myfileutil.py
# PURPOSE: crash-safe file writes and cross-process file locking
#
#  AUTHOR: Jason G Yates
#    DATE: 10-Nov-2026
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

import contextlib
import os
import tempfile

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None


# ------------ AtomicWrite ------------------------------------------------------
def AtomicWrite(path, data, mode=None):
    """Replace the contents of path with data so that readers (and the file
    after a crash or power loss) see either the old contents or the new
    contents, never a partial file.

    data may be str or bytes. mode, if given, sets the permissions of the new
    file (e.g. 0o600); otherwise the existing file's permissions are kept, or
    the umask default is used for a new file. When running as root the
    existing file's owner and group are preserved.
    """
    # write through symlinks to the real file rather than replacing the link
    path = os.path.realpath(path)
    directory = os.path.dirname(path) or "."

    existing = None
    try:
        existing = os.stat(path)
    except OSError:
        pass

    if mode is None:
        if existing is not None:
            mode = existing.st_mode & 0o7777
        else:
            umask = os.umask(0)
            os.umask(umask)
            mode = 0o666 & ~umask

    binary = isinstance(data, (bytes, bytearray))
    fd, tmp_path = tempfile.mkstemp(
        prefix="." + os.path.basename(path) + ".", suffix=".tmp", dir=directory
    )
    try:
        # mkstemp creates the file 0600, so secrets are never exposed while
        # being written; set the final mode before the file becomes visible
        if hasattr(os, "fchmod"):
            os.fchmod(fd, mode)
        if existing is not None and hasattr(os, "geteuid") and os.geteuid() == 0:
            try:
                os.fchown(fd, existing.st_uid, existing.st_gid)
            except OSError:
                pass
        with os.fdopen(fd, "wb" if binary else "w") as f:
            fd = None
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if not hasattr(os, "fchmod"):
            os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
        tmp_path = None
        _FsyncDirectory(directory)
    finally:
        if fd is not None:
            os.close(fd)
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ------------ _FsyncDirectory --------------------------------------------------
def _FsyncDirectory(directory):
    # make the rename itself durable; not supported on all platforms
    if not hasattr(os, "O_DIRECTORY"):
        return
    try:
        dir_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)


# ------------ FileLock ---------------------------------------------------------
@contextlib.contextmanager
def FileLock(path):
    """Exclusive lock shared between processes, held on a sidecar file
    (path + ".lock"). The data file itself can't be locked because
    AtomicWrite swaps in a new inode on every write. This is a no-op where
    fcntl isn't available or the lock file can't be created."""
    if fcntl is None:
        yield
        return
    lock_path = os.path.realpath(path) + ".lock"
    try:
        lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o666)
    except OSError:
        try:
            # lock file created by another user (e.g. root); flock works on
            # a read-only descriptor
            lock_fd = os.open(lock_path, os.O_RDONLY)
        except OSError:
            yield
            return
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)
