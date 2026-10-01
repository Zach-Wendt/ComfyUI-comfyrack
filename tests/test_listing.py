import os

import pytest

from comfyrack_pack.listing import list_outputs


def write(path, size=1, mtime=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def test_sorted_newest_first(tmp_path):
    write(tmp_path / "old.png", mtime=1_000)
    write(tmp_path / "newest.png", mtime=3_000)
    write(tmp_path / "middle.png", mtime=2_000)

    result = list_outputs(str(tmp_path))

    assert [f["filename"] for f in result["files"]] == ["newest.png", "middle.png", "old.png"]
    assert result["total"] == 3


def test_entry_shape_and_top_level_subfolder(tmp_path):
    write(tmp_path / "a.png", size=7, mtime=5_000)

    entry = list_outputs(str(tmp_path))["files"][0]

    assert entry == {
        "filename": "a.png",
        "subfolder": "",
        "type": "output",
        "size": 7,
        "mtime": 5_000.0,
    }


def test_nested_subfolder_uses_forward_slashes(tmp_path):
    nested = tmp_path / "ComfyUI" / "batch_01"
    nested.mkdir(parents=True)
    write(nested / "deep.png", mtime=9_000)

    entry = list_outputs(str(tmp_path))["files"][0]

    assert entry["filename"] == "deep.png"
    assert entry["subfolder"] == "ComfyUI/batch_01"
    assert "\\" not in entry["subfolder"]


def test_subfolder_argument_scopes_the_walk(tmp_path):
    write(tmp_path / "top.png", mtime=1_000)
    write(tmp_path / "picks" / "in.png", mtime=2_000)

    result = list_outputs(str(tmp_path), subfolder="picks")

    assert result["total"] == 1
    assert result["files"][0]["filename"] == "in.png"
    # The reported subfolder stays relative to the root, so /view can use it.
    assert result["files"][0]["subfolder"] == "picks"


def test_hidden_files_and_dirs_are_skipped(tmp_path):
    write(tmp_path / "visible.png", mtime=3_000)
    write(tmp_path / ".hidden.png", mtime=4_000)
    write(tmp_path / ".git" / "config", mtime=5_000)
    write(tmp_path / "sub" / ".secret", mtime=6_000)
    write(tmp_path / "sub" / "kept.png", mtime=1_000)

    result = list_outputs(str(tmp_path))

    assert [f["filename"] for f in result["files"]] == ["visible.png", "kept.png"]
    assert result["total"] == 2


def test_pagination_counts_everything(tmp_path):
    for index in range(5):
        write(tmp_path / f"{index}.png", mtime=1_000 + index)

    everything = list_outputs(str(tmp_path), limit=100)
    assert everything["total"] == 5
    assert everything["limit"] == 100
    assert everything["offset"] == 0

    page = list_outputs(str(tmp_path), limit=2, offset=2)
    assert page["total"] == 5  # total ignores pagination
    assert page["limit"] == 2
    assert page["offset"] == 2
    # Newest first, so the page starts at the third-newest file.
    assert [f["filename"] for f in page["files"]] == ["2.png", "1.png"]

    past_the_end = list_outputs(str(tmp_path), limit=2, offset=99)
    assert past_the_end["files"] == []
    assert past_the_end["total"] == 5


@pytest.mark.parametrize("given,expected", [(0, 1), (-5, 1), (200, 200), (5_000, 1_000)])
def test_limit_is_clamped(tmp_path, given, expected):
    write(tmp_path / "a.png")

    assert list_outputs(str(tmp_path), limit=given)["limit"] == expected


def test_negative_offset_is_clamped_to_zero(tmp_path):
    write(tmp_path / "a.png")

    assert list_outputs(str(tmp_path), offset=-3)["offset"] == 0


@pytest.mark.parametrize("subfolder", ["..", "../..", "sub/../../..", os.path.abspath(os.sep)])
def test_subfolder_cannot_escape_the_root(tmp_path, subfolder):
    write(tmp_path / "a.png")

    with pytest.raises(ValueError):
        list_outputs(str(tmp_path), subfolder=subfolder)


def test_absolute_subfolder_outside_root_is_rejected(tmp_path):
    elsewhere = tmp_path.parent / "elsewhere"
    elsewhere.mkdir()
    write(elsewhere / "a.png")

    with pytest.raises(ValueError):
        list_outputs(str(tmp_path), subfolder=str(elsewhere))


def test_missing_subfolder_is_empty(tmp_path):
    write(tmp_path / "a.png")

    result = list_outputs(str(tmp_path), subfolder="does/not/exist")

    assert result == {"files": [], "total": 0, "offset": 0, "limit": 200}
