"""Read-only instance facts: ComfyUI version, devices, queue depth, packs, models.

Every ComfyUI import lives inside a helper below, so importing this module
outside a running ComfyUI is harmless. Each sub-collection is fetched through
_collect(), which turns any failure into null instead of breaking the route --
a machine with no CUDA, a missing custom_nodes directory or a model folder that
throws must still answer with whatever *is* readable.
"""

import logging
import os
import socket

PACK_VERSION = "0.1.0"


def _collect(fn, *args):
    """Run a collector, returning None (and logging) if it raises."""
    try:
        return fn(*args)
    except Exception:
        logging.warning("comfyrack: could not collect %s", getattr(fn, "__name__", fn), exc_info=True)
        return None


def _comfyui_version():
    from comfyui_version import __version__

    return __version__


def _devices():
    import comfy.model_management as model_management

    device = model_management.get_torch_device()
    return [{
        "name": str(device),
        "vram_total": int(model_management.get_total_memory(device)),
        "vram_free": int(model_management.get_free_memory(device)),
    }]


def _queue():
    from server import PromptServer

    running, pending = PromptServer.instance.prompt_queue.get_current_queue_volatile()
    return {"running": len(running), "pending": len(pending)}


def _custom_node_packs():
    import folder_paths

    # Mirrors how ComfyUI itself walks custom_nodes/: directories are packs,
    # and a bare .py file is a single-file pack. Everything else (README,
    # .git, __pycache__, *.disabled) is skipped.
    names = set()
    for custom_nodes_dir in folder_paths.get_folder_paths("custom_nodes"):
        for entry in os.listdir(custom_nodes_dir):
            if entry.startswith(".") or entry == "__pycache__" or entry.endswith(".disabled"):
                continue
            if os.path.isdir(os.path.join(custom_nodes_dir, entry)) or entry.endswith(".py"):
                names.add(entry)
    return sorted(names)


def _models():
    import folder_paths

    return {
        folder_name: [name.replace("\\", "/") for name in folder_paths.get_filename_list(folder_name)]
        for folder_name in sorted(folder_paths.folder_names_and_paths)
        if folder_name != "custom_nodes"
    }


def collect_info():
    """Everything the /comfyrack/info route reports. Read-only, no side effects."""
    return {
        "pack_version": PACK_VERSION,
        "comfyui_version": _collect(_comfyui_version),
        "hostname": socket.gethostname(),
        "devices": _collect(_devices),
        "queue": _collect(_queue),
        "custom_node_packs": _collect(_custom_node_packs),
        "models": _collect(_models),
    }
