"""Unit tests for comfyrack_pack/share.py.

The real tailscale binary is never touched: every `tailscale ...` invocation is
intercepted by a fake `_run` that records each argument list and returns a
queued `subprocess.CompletedProcess`, and `_answers` is stubbed. `sys.platform`
is flipped where the module branches on it.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

import comfyrack_pack.share as share
from comfyrack_pack.share import ShareError


def _completed(args, returncode=0, stdout="", stderr=""):
    if isinstance(stdout, (dict, list)):
        stdout = json.dumps(stdout)
    if isinstance(stderr, (dict, list)):
        stderr = json.dumps(stderr)
    return subprocess.CompletedProcess(list(args), returncode, stdout, stderr)


class FakeRun:
    """Stand-in for ``share._run``: records every argument list and returns a queued reply."""

    def __init__(self):
        self.calls = []
        self._replies = {}  # tuple(args) -> CompletedProcess

    def reply(self, args, returncode=0, stdout="", stderr=""):
        self._replies[tuple(args)] = _completed(args, returncode, stdout, stderr)

    def __call__(self, args):
        args = list(args)
        self.calls.append(args)
        key = tuple(args)
        if key in self._replies:
            return self._replies[key]
        return _completed(args)

    def called_with(self, args):
        return list(args) in self.calls


class FakeAnswers:
    """Stand-in for ``share._answers``: a URL -> bool map (default False)."""

    def __init__(self):
        self.answers = {}

    def __call__(self, url):
        return self.answers.get(url, False)


@pytest.fixture
def fake_run(monkeypatch):
    run = FakeRun()
    monkeypatch.setattr(share, "_run", run)
    return run


@pytest.fixture
def fake_answers(monkeypatch):
    answers = FakeAnswers()
    monkeypatch.setattr(share, "_answers", answers)
    return answers


def _running(run, dns="m.x.ts.net."):
    run.reply(["status", "--json"], stdout={"BackendState": "Running", "Self": {"DNSName": dns}})


def _served_config(port=8188, proxy_port=8188):
    host = f"m.x.ts.net:{port}"
    return {"Web": {host: {"Handlers": {"/": {"Proxy": f"http://127.0.0.1:{proxy_port}"}}}}}


# --- _run: tailscale not installed -----------------------------------------

def test_run_without_tailscale_raises(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr(os, "name", "posix")  # skip the Windows default-path fallback

    with pytest.raises(ShareError) as exc:
        share._run(["status", "--json"])

    assert "tailscale.com/download" in exc.value.fix


# --- status: signed-in checks ------------------------------------------------

def test_status_not_signed_in(fake_run):
    fake_run.reply(["status", "--json"], stdout={"BackendState": "NeedsLogin"})

    with pytest.raises(ShareError) as exc:
        share.status(8188)

    assert "not signed in" in str(exc.value)
    assert "tailscale up" in exc.value.fix


def test_status_non_json_stdout_is_not_signed_in(fake_run):
    fake_run.reply(["status", "--json"], stdout="Tailscale is sad :(")

    with pytest.raises(ShareError) as exc:
        share.status(8188)

    assert "not signed in" in str(exc.value)
    assert "tailscale up" in exc.value.fix


def test_status_no_magicdns_name(fake_run):
    fake_run.reply(["status", "--json"], stdout={"BackendState": "Running", "Self": {"DNSName": ""}})

    with pytest.raises(ShareError) as exc:
        share.status(8188)

    assert "MagicDNS" in str(exc.value)


# --- status: running, served/not-served -------------------------------------

def test_status_running_not_shared(fake_run):
    _running(fake_run)
    fake_run.reply(["serve", "status", "--json"], stdout={})

    assert share.status(8188) == {"url": "http://m.x.ts.net:8188", "shared": False}


def test_status_running_shared(fake_run):
    _running(fake_run)
    fake_run.reply(["serve", "status", "--json"], stdout=_served_config())

    assert share.status(8188) == {"url": "http://m.x.ts.net:8188", "shared": True}


# --- enable ------------------------------------------------------------------

def test_enable_comfyui_not_answering(fake_run, fake_answers):
    _running(fake_run)
    fake_answers.answers = {"http://127.0.0.1:8188": False}

    with pytest.raises(ShareError) as exc:
        share.enable(8188)

    assert "does not answer" in str(exc.value)
    assert not fake_run.called_with(["serve", "--bg", "--http=8188", "http://127.0.0.1:8188"])


def test_enable_serves_exactly_once_when_not_shared(fake_run, fake_answers):
    _running(fake_run)
    fake_run.reply(["serve", "status", "--json"], stdout={})
    fake_run.reply(["serve", "--bg", "--http=8188", "http://127.0.0.1:8188"], returncode=0)
    fake_answers.answers = {
        "http://127.0.0.1:8188": True,
        "http://m.x.ts.net:8188": True,
    }

    result = share.enable(8188)

    assert result == {"url": "http://m.x.ts.net:8188", "shared": True}
    serve_call = ["serve", "--bg", "--http=8188", "http://127.0.0.1:8188"]
    assert fake_run.calls.count(serve_call) == 1


def test_enable_skips_serve_when_already_served(fake_run, fake_answers):
    _running(fake_run)
    fake_run.reply(["serve", "status", "--json"], stdout=_served_config())
    fake_answers.answers = {
        "http://127.0.0.1:8188": True,
        "http://m.x.ts.net:8188": True,
    }

    result = share.enable(8188)

    assert result == {"url": "http://m.x.ts.net:8188", "shared": True}
    assert not fake_run.called_with(["serve", "--bg", "--http=8188", "http://127.0.0.1:8188"])


def test_enable_serve_denied_on_linux(fake_run, fake_answers, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    _running(fake_run)
    fake_run.reply(["serve", "status", "--json"], stdout={})
    fake_run.reply(["serve", "--bg", "--http=8188", "http://127.0.0.1:8188"],
                   returncode=1, stderr="Access denied")
    fake_answers.answers = {"http://127.0.0.1:8188": True}

    with pytest.raises(ShareError) as exc:
        share.enable(8188)

    assert "sudo tailscale set --operator=$USER" in exc.value.fix


def test_enable_serve_denied_on_windows(fake_run, fake_answers, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    _running(fake_run)
    fake_run.reply(["serve", "status", "--json"], stdout={})
    fake_run.reply(["serve", "--bg", "--http=8188", "http://127.0.0.1:8188"],
                   returncode=1, stderr="Access denied")
    fake_answers.answers = {"http://127.0.0.1:8188": True}

    with pytest.raises(ShareError) as exc:
        share.enable(8188)

    assert str(exc.value).startswith("tailscale serve failed")


def test_enable_tsnet_url_not_answering(fake_run, fake_answers):
    _running(fake_run)
    fake_run.reply(["serve", "status", "--json"], stdout={})
    fake_run.reply(["serve", "--bg", "--http=8188", "http://127.0.0.1:8188"], returncode=0)
    fake_answers.answers = {
        "http://127.0.0.1:8188": True,
        "http://m.x.ts.net:8188": False,
    }

    with pytest.raises(ShareError) as exc:
        share.enable(8188)

    assert "does not answer" in str(exc.value)


# --- disable -----------------------------------------------------------------

def test_disable_when_served(fake_run):
    _running(fake_run)
    fake_run.reply(["serve", "status", "--json"], stdout=_served_config())
    fake_run.reply(["serve", "--http=8188", "off"], returncode=0)

    result = share.disable(8188)

    assert result == {"url": "http://m.x.ts.net:8188", "shared": False}
    assert fake_run.called_with(["serve", "--http=8188", "off"])


def test_disable_when_not_served(fake_run):
    _running(fake_run)
    fake_run.reply(["serve", "status", "--json"], stdout={})

    result = share.disable(8188)

    assert result == {"url": "http://m.x.ts.net:8188", "shared": False}
    assert not fake_run.called_with(["serve", "--http=8188", "off"])


# --- _is_served: a proxy to a different port is not "served" -----------------

def test_is_served_ignores_proxy_to_other_port(fake_run):
    _running(fake_run)
    fake_run.reply(["serve", "status", "--json"], stdout=_served_config(proxy_port=9000))

    assert share.status(8188)["shared"] is False


# --- is_local_request --------------------------------------------------------

@pytest.mark.parametrize("remote,headers", [
    ("127.0.0.1", {"Host": "127.0.0.1:8188"}),
    ("::1", {"Host": "[::1]:8188"}),
    ("127.0.0.1", {"Host": "localhost:8188"}),
])
def test_is_local_request_true(remote, headers):
    assert share.is_local_request(remote, headers) is True


def test_is_local_request_false_for_tailnet_peer():
    assert share.is_local_request("100.64.0.5", {"Host": "m.x.ts.net:8188"}) is False


def test_is_local_request_false_for_tsnet_host():
    # A tailscale serve request arrives from 127.0.0.1 but keeps the ts.net Host.
    assert share.is_local_request("127.0.0.1", {"Host": "m.x.ts.net:8188"}) is False


@pytest.mark.parametrize("header", ["X-Forwarded-For", "Forwarded", "Tailscale-User-Login"])
def test_is_local_request_false_when_forwarded_header_present(header):
    headers = {"Host": "127.0.0.1:8188", header: "1.2.3.4"}
    assert share.is_local_request("127.0.0.1", headers) is False


def test_is_local_request_false_when_host_missing():
    assert share.is_local_request("127.0.0.1", {}) is False
