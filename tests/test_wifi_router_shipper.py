"""Hermetic tests for tools/wifi-router/wifi_router_shipper.py.

No live network access: the router admin API is emulated with a local
http.server instance and all crypto expectations are hardcoded vectors.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Load the shipper script as a module without polluting the package namespace
# (same pattern as test_threat_intel_sync.py).
_spec = importlib.util.spec_from_file_location(
    "wifi_router_shipper", REPO_ROOT / "tools" / "wifi-router" / "wifi_router_shipper.py"
)
shipper = importlib.util.module_from_spec(_spec)
sys.modules["wifi_router_shipper"] = shipper
_spec.loader.exec_module(shipper)

# Test credentials used throughout (never a real router).
TEST_USER = "admin"
TEST_PASS = "s3cret"
LOGIN_TOKEN = "tok123"

# Independently computed vectors (hardcoded so the test does not re-derive
# expectations from the implementation under test).
EXPECTED_USER_ENC = (
    "edbd881f1ee2f76ba0bd70fd184f87711be991a0401fd07ccd4b199665f00761"
    "afc91731d8d8ba6cbb188b2ed5bfb465b9f3d30231eb0430b9f90fe91d136648"
)
EXPECTED_PASS_ENC = (
    "e00e426ea1299e00cdd15efddd90c04b2d0facd90c60c9927895e8b1224fa90b"
    "6c7eb6eb4e56f82f29b1d6ad844d061ddbea03f416d6894ea154329f8dc70bf1"
)

SYS_LOG = (
    "2026 Oct 11 08:08:01 info arc_wlsta_monitor: [WIFI.6][SYS]BSS=wl0.1 ACTION=disassociate, STA=0e:98:dc:c5:b7:ea\n"
    "2026 Oct 11 11:16:09 info arc_wlsta_monitor: [WIFI.6][SYS]BSS=wl0.1 ACTION=associate, STA=f8:3d:c6:0f:6f:76"
)
FW_LOG = (
    "2026 Oct 11 02:13:43 info kernel: [FW] IPTABLES Block IN=eth4 SRC=27.39.169.40 DST=108.7.40.60\n"
    "2026 Oct 11 02:33:52 info dhcpc.sh: [WAN.6][WDHCP] renew IP: 108.7.40.60"
)


# ---------------------------------------------------------------------------
# Fake router
# ---------------------------------------------------------------------------

class _FakeRouterHandler(BaseHTTPRequestHandler):
    """Emulates the G3100 CGI endpoints the shipper talks to."""

    state: dict = {}

    def log_message(self, *_args):  # keep pytest output clean
        pass

    def _cookie(self) -> str | None:
        raw = self.headers.get("Cookie", "")
        for part in raw.split(";"):
            part = part.strip()
            if part.startswith("sysauth="):
                return part.split("=", 1)[1]
        return None

    def _send(self, code: int, body: str, content_type: str = "application/json",
              extra_headers: dict | None = None):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _read_form(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8")
        return dict(urllib.parse.parse_qsl(raw))

    def do_GET(self):
        state = self.state
        if self.path == "/loginStatus.cgi":
            logged_in = bool(state["session"]) and self._cookie() == state["session"]
            self._send(200, json.dumps({
                "islogin": "1" if logged_in else "0",
                "loginToken": LOGIN_TOKEN,
                "token": "formtok456" if logged_in else "",
                "wizard": "1",
                "expires": "600",
            }))
        elif self.path.startswith("/log/messages_") and self.path.endswith(".log"):
            tab = self.path[len("/log/messages_"):-len(".log")]
            if not state["session"] or self._cookie() != state["session"]:
                self._send(403, json.dumps({"flag": 0}))
                return
            self._send(200, state["tabs"].get(tab, ""), content_type="text/plain")
        else:
            self._send(404, "{}")

    def do_POST(self):
        state = self.state
        form = self._read_form()
        if self.path == "/login.cgi":
            if state["bad_creds"]:
                self._send(403, json.dumps({"flag": 1}))
                return
            ok = (
                form.get("luci_username") == EXPECTED_USER_ENC
                and form.get("luci_password") == EXPECTED_PASS_ENC
                and form.get("luci_token") == LOGIN_TOKEN
                and form.get("luci_view") == "Desktop"
            )
            if ok:
                state["session"] = "sess123"
                self._send(200, "<html>ok</html>", content_type="text/html",
                           extra_headers={"Set-Cookie": "sysauth=sess123; path=/"})
            else:
                self._send(403, json.dumps({"flag": 1}))
        elif self.path == "/logout.cgi":
            if form.get("token") == "formtok456":
                state["session"] = None
            self._send(200, "{}")
        else:
            self._send(404, "{}")


@pytest.fixture()
def fake_router():
    state = {
        "session": None,
        "bad_creds": False,
        "tabs": {
            "SYS": SYS_LOG,
            "SECURITY": "",
            "ADV": "",
            "FW": FW_LOG,
            "WDHCP": "",
            "LDHCP": "",
        },
    }
    handler = type("BoundHandler", (_FakeRouterHandler,), {"state": state})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield {"url": f"http://127.0.0.1:{httpd.server_address[1]}", "state": state}
    httpd.shutdown()
    thread.join(timeout=5)


def make_shipper(tmp_path: Path, url: str, **overrides) -> shipper.WifiRouterShipper:
    env = {
        "WIFI_ROUTER_ADDRESS": url,
        "WIFI_ROUTER_USERNAME": TEST_USER,
        "WIFI_ROUTER_PASSWORD": TEST_PASS,
        "WIFI_ROUTER_POLL_SECONDS": "60",
        "OUTPUT_DIR": str(tmp_path),
    }
    env.update(overrides)
    return shipper.WifiRouterShipper(env)


# ---------------------------------------------------------------------------
# Crypto encoding vectors
# ---------------------------------------------------------------------------

def test_username_encoding_matches_spa():
    assert shipper.encode_username(TEST_USER) == EXPECTED_USER_ENC


def test_password_encoding_with_token():
    assert shipper.encode_password(TEST_PASS, LOGIN_TOKEN) == EXPECTED_PASS_ENC


def test_password_encoding_without_token_falls_back_to_arc_md5():
    # login_encode(pass, "") == ArcMD5(pass) == SHA512(MD5(pass))
    assert shipper.encode_password(TEST_PASS, "") == shipper.arc_md5(TEST_PASS)


# ---------------------------------------------------------------------------
# Line parsing
# ---------------------------------------------------------------------------

def test_parse_line_full():
    record = shipper.parse_line(
        "2026 Oct 11 08:08:01 info arc_wlsta_monitor: [WIFI.6][SYS]BSS=wl0.1 ACTION=associate",
        "SYS", "2026-10-12T00:00:00+00:00",
    )
    assert record["timestamp"] == "2026-10-11T08:08:01"
    assert record["severity"] == "info"
    assert record["process"] == "arc_wlsta_monitor"
    assert record["log_type"] == "SYS"
    assert record["message"] == "[WIFI.6][SYS]BSS=wl0.1 ACTION=associate"


def test_parse_line_keeps_colons_in_message():
    record = shipper.parse_line(
        "2026 Oct 11 02:33:52 info dhcpc.sh: [WAN.6][WDHCP] renew IP: 108.7.40.60",
        "WDHCP", "2026-10-12T00:00:00+00:00",
    )
    assert record["process"] == "dhcpc.sh"
    assert record["message"] == "[WAN.6][WDHCP] renew IP: 108.7.40.60"


def test_parse_line_single_digit_day_pads():
    record = shipper.parse_line(
        "2026 Oct  2 03:04:05 warn kernel: [FW] something",
        "FW", "2026-10-12T00:00:00+00:00",
    )
    assert record["timestamp"] == "2026-10-02T03:04:05"
    assert record["severity"] == "warn"


def test_parse_line_unparseable_keeps_raw_message():
    record = shipper.parse_line("<<< garbled >>>", "SYS", "2026-10-12T00:00:00+00:00")
    assert record["timestamp"] is None
    assert record["severity"] is None
    assert record["process"] is None
    assert record["message"] == "<<< garbled >>>"


# ---------------------------------------------------------------------------
# Dedup state + rotation
# ---------------------------------------------------------------------------

def test_ship_state_roundtrip(tmp_path):
    path = tmp_path / "state.json.gz"
    state = shipper.ShipState(path, ring_size=3)
    state.remember("aaaa")
    state.remember("bbbb")
    state.tab_sha["SYS"] = "sha-of-sys"
    state.save()

    reloaded = shipper.ShipState(path, ring_size=3)
    assert reloaded.seen("aaaa") and reloaded.seen("bbbb")
    assert reloaded.tab_sha == {"SYS": "sha-of-sys"}
    # State is gzipped to keep the hash-ring file small on disk.
    assert path.read_bytes()[:2] == b"\x1f\x8b"


def test_ship_state_ring_evicts_oldest(tmp_path):
    state = shipper.ShipState(tmp_path / "state.json", ring_size=2)
    state.remember("one")
    state.remember("two")
    state.remember("three")  # evicts "one"
    assert not state.seen("one")
    assert state.seen("two") and state.seen("three")


def test_ship_state_corrupt_file_starts_clean(tmp_path):
    path = tmp_path / "state.json.gz"
    path.write_text("{not json")
    state = shipper.ShipState(path, ring_size=10)
    assert not state.seen("anything")
    assert state.tab_sha == {}


def test_ship_state_save_debounced_unless_forced(tmp_path):
    import time as _time
    path = tmp_path / "state.json.gz"
    state = shipper.ShipState(path, ring_size=10)
    state.dirty = True
    state._last_saved = _time.monotonic()  # just saved -> nothing due yet
    state.save_if_due()
    assert not path.exists()
    state.save_if_due(force=True)  # shutdown path always persists
    assert path.exists()


def test_default_ring_size_covers_all_tabs_combined():
    # The ADV tab alone keeps ~60k lines; the ring must hold more hashes than
    # all tabs combined or lines evicted mid-backfill get re-emitted forever
    # (observed live: 57k duplicates per poll with a 30k ring).
    assert shipper.DEFAULT_RING_SIZE >= 100_000


def test_rotate_if_needed(tmp_path):
    path = tmp_path / "router_logs.jsonl"
    path.write_text("x" * 100)
    inode_before = path.stat().st_ino
    assert shipper.rotate_if_needed(path, max_bytes=50)
    # copytruncate: the active file keeps its inode and is truncated in place,
    # so the collector's open descriptor keeps tailing without a gap.
    assert path.exists()
    assert path.stat().st_size == 0
    assert path.stat().st_ino == inode_before
    rotated = tmp_path / "router_logs.jsonl.1"
    assert rotated.exists() and rotated.read_text() == "x" * 100
    # Second rotation replaces the previous .1 file.
    path.write_text("y" * 80)
    assert shipper.rotate_if_needed(path, max_bytes=50)
    assert rotated.read_text() == "y" * 80
    # Under the cap: no rotation.
    path.write_text("z" * 10)
    assert not shipper.rotate_if_needed(path, max_bytes=50)


# ---------------------------------------------------------------------------
# End-to-end poll cycle against the fake router
# ---------------------------------------------------------------------------

def test_poll_cycle_backfill_dedup_and_incremental(tmp_path, fake_router):
    sp = make_shipper(tmp_path, fake_router["url"])
    emitted = sp.poll_once()
    assert emitted == 4  # 2 SYS + 2 FW lines across the default tabs

    lines = (tmp_path / "router_logs.jsonl").read_text().splitlines()
    assert len(lines) == 4
    first = json.loads(lines[0])
    assert first["log_type"] == "SYS"
    assert first["timestamp"] == "2026-10-11T08:08:01"
    assert first["severity"] == "info"
    assert first["process"] == "arc_wlsta_monitor"
    assert "observed_time" in first
    for line in lines:
        record = json.loads(line)  # every line must be valid JSON
        assert record["message"]

    # No changes -> nothing emitted, no logout/login churn errors.
    assert sp.poll_once() == 0

    # One new firewall line -> exactly one new record.
    fake_router["state"]["tabs"]["FW"] += (
        "\n2026 Oct 12 22:00:00 info kernel: [FW] IPTABLES Block SRC=9.9.9.9"
    )
    assert sp.poll_once() == 1
    assert len((tmp_path / "router_logs.jsonl").read_text().splitlines()) == 5
    # State persisted for restart dedup.
    assert (tmp_path / "state.json.gz").exists()


def test_emission_budget_chunks_backfill(tmp_path, fake_router):
    """Large backfills ramp over several polls instead of bursting."""
    sp = make_shipper(tmp_path, fake_router["url"], WIFI_ROUTER_MAX_RECORDS_PER_POLL="1")
    assert sp.poll_once() == 1
    assert sp.poll_once() == 1
    assert sp.poll_once() == 1
    assert sp.poll_once() == 1
    # All four lines emitted exactly once across the chunked polls.
    lines = (tmp_path / "router_logs.jsonl").read_text().splitlines()
    assert len(lines) == 4
    assert len({line for line in lines}) == 4
    # Budget exhausted: nothing left, and a fresh line still flows.
    assert sp.poll_once() == 0
    fake_router["state"]["tabs"]["FW"] += (
        "\n2026 Oct 12 23:00:00 info kernel: [FW] IPTABLES Block SRC=8.8.8.8"
    )
    assert sp.poll_once() == 1


def test_restart_does_not_reemit(tmp_path, fake_router):
    sp = make_shipper(tmp_path, fake_router["url"])
    assert sp.poll_once() == 4
    # Simulate a container restart: brand-new shipper instance, same state dir.
    sp2 = make_shipper(tmp_path, fake_router["url"])
    assert sp2.poll_once() == 0


def test_bad_credentials_raise_login_error(tmp_path, fake_router):
    fake_router["state"]["bad_creds"] = True
    sp = make_shipper(tmp_path, fake_router["url"])
    with pytest.raises(shipper.LoginError, match="invalid credentials"):
        sp.poll_once()
    assert not (tmp_path / "router_logs.jsonl").exists()


def test_lapsed_session_surfaces_login_error(tmp_path, fake_router):
    sp = make_shipper(tmp_path, fake_router["url"])
    client = sp._ensure_client()
    client.login()
    assert client.logged_in
    fake_router["state"]["session"] = None  # router drops the session
    with pytest.raises(shipper.LoginError):
        client.fetch_tab("SYS")
    assert client.logged_in is False


def test_logout_releases_session(tmp_path, fake_router):
    sp = make_shipper(tmp_path, fake_router["url"])
    client = sp._ensure_client()
    client.login()
    assert fake_router["state"]["session"] == "sess123"
    client.logout()
    assert fake_router["state"]["session"] is None
    assert not client.logged_in


# ---------------------------------------------------------------------------
# Configuration handling
# ---------------------------------------------------------------------------

def test_unconfigured_shipper_reports_not_configured():
    sp = shipper.WifiRouterShipper({})
    assert not sp.configured


def test_address_fragment_is_stripped():
    sp = shipper.WifiRouterShipper({
        "WIFI_ROUTER_ADDRESS": "https://192.168.1.1/#/login/",
        "WIFI_ROUTER_USERNAME": "admin",
        "WIFI_ROUTER_PASSWORD": "x",
    })
    assert sp.address == "https://192.168.1.1"


def test_tabs_are_configurable(tmp_path, fake_router):
    sp = make_shipper(tmp_path, fake_router["url"], WIFI_ROUTER_TABS="sys, fw")
    assert sp.tabs == ("SYS", "FW")
    assert sp.poll_once() == 4
