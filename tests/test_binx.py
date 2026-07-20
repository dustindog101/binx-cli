import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("binx", ROOT / "binx.py")
binx = importlib.util.module_from_spec(spec)
sys.modules["binx"] = binx
spec.loader.exec_module(binx)


def test_version():
    assert binx.__version__
    assert binx.DOMAIN == "binx.cz"
    assert "binx.cz" in binx.API


def test_parse_favorite_tokens_quoted_note():
    pairs = binx.parse_favorite_tokens(["539689", '"good for prizepicks"'])
    assert pairs == [("539689", "good for prizepicks")]


def test_parse_favorite_tokens_toggle():
    pairs = binx.parse_favorite_tokens(["486796", "400895"])
    assert pairs == [("486796", None), ("400895", None)]


def test_parse_favorite_tokens_flag_note():
    pairs = binx.parse_favorite_tokens(["539689", "--note", "cashapp bin"])
    assert pairs == [("539689", "cashapp bin")]


def test_is_connectivity_error():
    assert binx.is_connectivity_error("Could not resolve host: api.binx.vip")
    assert binx.is_connectivity_error("HTTP 502")
    assert not binx.is_connectivity_error("invalid BIN format")


def test_parse_favorite_tokens_shell_note():
    pairs = binx.parse_favorite_tokens(["539689", "good for prizepicks"])
    assert pairs == [("539689", "good for prizepicks")]


def test_version_tuple():
    assert binx._version_tuple("1.1.0") > binx._version_tuple("1.0.9")


def test_compare_versions():
    assert binx._compare_versions("1.0.0", "1.1.0") == "update_available"
    assert binx._compare_versions("1.1.0", "1.1.0") == "up_to_date"


def test_check_for_updates_offline_preserves_cache(monkeypatch):
    monkeypatch.setattr(binx, "fetch_latest_release", lambda *a, **k: (None, "offline"))
    monkeypatch.setattr(binx, "_read_update_cache", lambda: {
        "checked_at": 0, "latest": "9.9.9", "status": "update_available", "url": "http://x"
    })
    info = binx.check_for_updates(force=True)
    assert info["latest"] == "9.9.9"
    assert info["error"] == "offline"


def test_validate_script(tmp_path):
    p = tmp_path / "binx.py"
    p.write_text('__version__ = "1.0"\ndef fetch_bin(): pass')
    assert binx._validate_script(p)

