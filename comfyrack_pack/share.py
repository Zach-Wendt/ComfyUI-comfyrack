"""Share this ComfyUI on the user's Tailscale tailnet (the same three steps as `comfyrack share`).

Check Tailscale is installed and signed in, check ComfyUI answers locally, run
`tailscale serve --bg`. A failure raises ShareError whose `fix` is a one-line next step."""
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from urllib.parse import urlsplit

_WIN_DEFAULT = r"C:\Program Files\Tailscale\tailscale.exe"


class ShareError(Exception):
    def __init__(self, message, fix):
        super().__init__(message)
        self.fix = fix


def _run(args):
    exe = shutil.which("tailscale")
    if exe is None and os.name == "nt" and os.path.isfile(_WIN_DEFAULT):
        exe = _WIN_DEFAULT
    if exe is None:
        raise ShareError("Tailscale is not installed",
                         "install it from https://tailscale.com/download, sign in, then switch this on again")
    return subprocess.run([exe, *args], capture_output=True, text=True, timeout=30)


def _answers(url):
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/system_stats", timeout=5) as r:
            return r.status == 200
    except OSError:
        return False


def _json(proc):
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return {}


def _dns_name():
    data = _json(_run(["status", "--json"]))
    if data.get("BackendState") != "Running":
        raise ShareError("Tailscale is not signed in", "run `tailscale up`, sign in, then switch this on again")
    name = (data.get("Self") or {}).get("DNSName", "").rstrip(".")
    if not name:
        raise ShareError("Tailscale has no MagicDNS name for this machine",
                         "turn on MagicDNS in the Tailscale admin console (DNS tab)")
    return name


def _is_served(port):
    web = _json(_run(["serve", "status", "--json"])).get("Web") or {}
    target = f"http://127.0.0.1:{port}"
    return any(host.endswith(f":{port}") and h.get("Proxy") == target
               for host, cfg in web.items() for h in (cfg.get("Handlers") or {}).values())


def status(port):
    return {"url": f"http://{_dns_name()}:{port}", "shared": _is_served(port)}


def enable(port):
    dns = _dns_name()
    if not _answers(f"http://127.0.0.1:{port}"):
        raise ShareError(f"ComfyUI does not answer on 127.0.0.1:{port}", "check the port ComfyUI runs on")
    url = f"http://{dns}:{port}"
    if not _is_served(port):
        proc = _run(["serve", "--bg", f"--http={port}", f"http://127.0.0.1:{port}"])
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout).strip()
            if sys.platform.startswith("linux") and ("denied" in err.lower() or "operator" in err.lower()):
                raise ShareError("Tailscale refused to serve for this user",
                                 "run once: sudo tailscale set --operator=$USER")
            raise ShareError(f"tailscale serve failed: {err.splitlines()[-1] if err else proc.returncode}",
                             "run `tailscale serve status` to see what is set")
    if not _answers(url):
        raise ShareError(f"{url} does not answer from this machine",
                         "check Tailscale is connected and MagicDNS is on, then retry")
    return {"url": url, "shared": True}


def disable(port):
    dns = _dns_name()
    if _is_served(port):
        proc = _run(["serve", f"--http={port}", "off"])
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout).strip()
            raise ShareError(f"tailscale serve off failed: {err.splitlines()[-1] if err else proc.returncode}",
                             "run `tailscale serve status` to see what is set")
    return {"url": f"http://{dns}:{port}", "shared": False}


def is_local_request(remote, headers):
    """True only for a browser on this machine. `tailscale serve` proxies from 127.0.0.1, so the
    peer address alone cannot tell a tailnet caller from a local one: the Host header (the proxy
    keeps the ts.net name) and the forwarding headers must be local too."""
    host = urlsplit("//" + (headers.get("Host") or "")).hostname
    return (remote in ("127.0.0.1", "::1") and host in ("127.0.0.1", "localhost", "::1")
            and not any(h in headers for h in ("X-Forwarded-For", "Forwarded", "Tailscale-User-Login")))
