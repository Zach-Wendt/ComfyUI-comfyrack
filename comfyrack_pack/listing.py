"""Recursive listing of an output directory, shaped for ComfyUI's GET /view.

Pure stdlib on purpose: nothing here imports ComfyUI, so the file can be unit
tested (and reasoned about) outside a running ComfyUI process.

Every entry exposes "filename", "subfolder" and "type" -- exactly the three
query parameters ComfyUI's core `GET /view` accepts -- so a client can turn any
listed entry into a URL and fetch the file without knowing the output layout.
"""

import os

DEFAULT_LIMIT = 200
MIN_LIMIT = 1
MAX_LIMIT = 1000

# Value ComfyUI's /view uses for files living under folder_paths.get_output_directory().
OUTPUT_TYPE = "output"


def _is_within(root, target):
    """True when target is root itself or lives underneath it.

    os.path.commonpath raises ValueError when the two paths sit on different
    drives (Windows); that is an escape, not a crash.
    """
    try:
        return os.path.commonpath((root, target)) == root
    except ValueError:
        return False


def _resolve_start(root_abs, subfolder):
    """Absolute directory to walk, guaranteed to stay inside root_abs."""
    if not subfolder:
        return root_abs
    # os.path.join() throws `root_abs` away when subfolder is absolute, and a
    # ".." segment escapes from anywhere, so both need checking explicitly.
    start = os.path.abspath(os.path.join(root_abs, subfolder))
    if not _is_within(root_abs, start):
        raise ValueError(f"subfolder {subfolder!r} resolves outside the output directory")
    return start


def list_outputs(root, subfolder="", limit=DEFAULT_LIMIT, offset=0):
    """List files under root/subfolder, newest first.

    Returns {"files": [...], "total": N, "offset": o, "limit": l} where "total"
    counts every visible file under the subfolder, not just the returned page.
    Raises ValueError if subfolder would escape root. A missing subfolder (or a
    root that does not exist) yields an empty page.
    """
    root_abs = os.path.abspath(root)
    start = _resolve_start(root_abs, subfolder)

    limit = max(MIN_LIMIT, min(int(limit), MAX_LIMIT))
    offset = max(0, int(offset))

    # Walk the whole tree first: "total" has to describe the subfolder, not the
    # page, and sorting has to happen before slicing for paging to be repeatable.
    # Tuples (mtime, subfolder, filename, size) are cheaper than dicts to hold.
    entries = []
    if os.path.isdir(start):
        for dirpath, dirnames, filenames in os.walk(start):
            # Hidden directories (and, below, hidden files) stay invisible.
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            relative = os.path.relpath(dirpath, root_abs)
            # "" at the top level, "a/b" below it -- never an OS-specific separator.
            relative = "" if relative == os.curdir else relative.replace(os.sep, "/")
            for name in filenames:
                if name.startswith("."):
                    continue
                try:
                    stat = os.stat(os.path.join(dirpath, name))
                except OSError:
                    continue
                entries.append((stat.st_mtime, relative, name, stat.st_size))

    # Newest first, with a name tie-break so equal mtimes still page consistently.
    entries.sort(key=lambda entry: (-entry[0], entry[1], entry[2]))

    files = [
        {
            "filename": name,
            "subfolder": relative,
            "type": OUTPUT_TYPE,
            "size": size,
            "mtime": mtime,
        }
        for mtime, relative, name, size in entries[offset:offset + limit]
    ]
    return {"files": files, "total": len(entries), "offset": offset, "limit": limit}
