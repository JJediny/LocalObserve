#!/usr/bin/env python3
"""wifi_router_shipper.py — pull router syslog over the web admin API into JSONL.

Some home routers (e.g. the Verizon Fios G3100) expose no syslog/RSYSLOG
forwarding at all; their log tabs only exist behind the web management UI.
This shipper polls that UI with the admin credentials, fetches every log tab,
deduplicates lines across polls/restarts, and appends new records as JSONL for
the otel-collector's ``file_log/router`` receiver to tail into OpenObserve
(stream ``router-logs``) and rsigma.

Design constraints honored here (see AGENTS.md):
  * stdlib only — no third-party deps, no uv.lock churn;
  * no secrets in logs;
  * graceful idle when unconfigured (so a default ``docker compose up`` on a
    host without these env vars stays green — the service has no healthcheck
    on purpose, verify-runtimes.sh must not fail on router-less hosts);
  * bounded disk use via size-based JSONL rotation;
  * large first-run backfills ramp in chunked per-poll emissions so the
    collector's memory_limiter is never burst;
  * bounded SSD churn: state is gzipped and rewritten only when dirty.

Fios G3100 protocol (reverse-engineered from the router's Vue SPA,
firmware assets last-modified 2026-07-09):
  GET  /loginStatus.cgi          -> {"islogin","loginToken","token","expires"}
  POST /login.cgi                form: luci_username = SHA512(MD5(username))
                                         luci_password = SHA512(loginToken + SHA512(MD5(password)))
                                         luci_view = Desktop|Mobile
                                         luci_token = <loginToken>
                                         luci_keep_login = 0|1
                                    success: HTTP 200 + ``sysauth`` cookie
                                    failure: HTTP 403 + JSON flag (1=bad creds,
                                    2=max sessions, 7=lockout)
  GET  /log/messages_<TAB>.log   plain text, one entry per line:
                                    "YYYY Mmm DD HH:MM:SS level process: msg"
  POST /logout.cgi               form: token=<form token from loginStatus>

The G3100 allows at most 2 concurrent admin sessions ("maxsession": 2) and
expires idle sessions after ~600s, so each poll cycle logs in, fetches, and
logs out again instead of holding a session open.
"""
from __future__ import annotations

import gzip
import hashlib
import http.cookiejar
import json
import logging
import os
import re
import shutil
import signal
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

LOG = logging.getLogger("wifi-router-shipper")

DEFAULT_TABS = ("SYS", "SECURITY", "ADV", "FW", "WDHCP", "LDHCP")
DEFAULT_OUTPUT_DIR = "/var/log/wifi-router"
DEFAULT_POLL_SECONDS = 60
DEFAULT_MAX_OUTPUT_BYTES = 16 * 1024 * 1024  # rotate the JSONL at 16 MiB
# Dedup ring must hold MORE lines than all router tabs combined (the ADV tab
# alone keeps ~60k lines): any line whose hash falls out of the ring would be
# re-emitted on the next poll. 150k gives >2x headroom over the observed
# ~67k total.
DEFAULT_RING_SIZE = 150_000
# Cap records emitted per poll so a first-run backfill (~60k lines) ramps in
# ~4 polls instead of bursting through the collector's memory_limiter.
DEFAULT_MAX_RECORDS_PER_POLL = 15_000
# State is rewritten only when dirty and at most this often (SSD wear).
STATE_SAVE_INTERVAL_SECONDS = 300
OUTPUT_FILENAME = "router_logs.jsonl"
STATE_FILENAME = "state.json.gz"
STATE_VERSION = 1

MONTHS = {
    name: idx
    for idx, name in enumerate(
        ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
         "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
        start=1,
    )
}

# "2026 Oct 11 08:08:01 info arc_wlsta_monitor: [WIFI.6][SYS]..."
#  <year> <mon> <day> <time>     <sev>  <process>:      <message>
LINE_RE = re.compile(
    r"^(\d{4})\s+([A-Za-z]{3})\s+(\d{1,2})\s+(\d{2}:\d{2}:\d{2})"
    r"\s+(\S+)\s+([^:\s]+):\s?(.*)$"
)

LOGIN_FLAG_HINTS = {
    1: "invalid credentials (check WIFI_ROUTER_USERNAME/WIFI_ROUTER_PASSWORD)",
    2: "router session limit reached; waiting for a session to expire",
    3: "session state changed on the router; will retry",
    7: "too many login attempts; router-imposed lockout active",
}


class RouterError(Exception):
    """Transport-level failure (network unreachable, timeout, TLS...)."""


class LoginError(RouterError):
    """The router rejected the login (bad credentials, session limit...)."""


# --------------------------------------------------------------------------
# Crypto helpers (mirror the SPA's do_encode/login_encode/ArcMD5)
# --------------------------------------------------------------------------

def md5_hex(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def sha512_hex(value: str) -> str:
    return hashlib.sha512(value.encode("utf-8")).hexdigest()


def arc_md5(value: str) -> str:
    # The SPA names this "ArcMD5" but it is SHA-512(MD5(x)) hex, not MD5.
    return sha512_hex(md5_hex(value))


def encode_username(username: str) -> str:
    # do_encode(username, true) in the SPA.
    return arc_md5(username)


def encode_password(password: str, login_token: str) -> str:
    # login_encode(password, loginToken) in the SPA:
    # SHA-512(loginToken + ArcMD5(password)); plain ArcMD5 when no token.
    if not login_token:
        return arc_md5(password)
    return sha512_hex(login_token + arc_md5(password))


# --------------------------------------------------------------------------
# Log line parsing
# --------------------------------------------------------------------------

def parse_timestamp(year: str, month_abbr: str, day: str, hms: str) -> str | None:
    month = MONTHS.get(month_abbr.title())
    if month is None:
        return None
    return f"{year}-{month:02d}-{int(day):02d}T{hms}"


def parse_line(raw: str, log_type: str, observed_time: str) -> dict:
    """Parse one router log line into the JSONL record shape.

    Unparseable lines are still emitted (message = raw line) so nothing the
    router reports is silently dropped; they simply lack parsed fields.
    """
    match = LINE_RE.match(raw)
    if not match:
        return {
            "timestamp": None,
            "observed_time": observed_time,
            "log_type": log_type,
            "severity": None,
            "process": None,
            "message": raw,
        }
    year, month_abbr, day, hms, severity, process, message = match.groups()
    return {
        "timestamp": parse_timestamp(year, month_abbr, day, hms),
        "observed_time": observed_time,
        "log_type": log_type,
        "severity": severity.lower(),
        "process": process,
        "message": message,
    }


def line_hash(raw: str) -> str:
    # 16 hex chars is collision-safe for dedup purposes and keeps state small.
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:16]


# --------------------------------------------------------------------------
# HTTP client for the router admin API
# --------------------------------------------------------------------------

class FiosClient:
    """Minimal client for the Fios G3100 CGI admin API (stdlib only)."""

    def __init__(self, base_url: str, username: str, password: str,
                 verify_tls: bool = False, timeout: int = 20):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        context = ssl.create_default_context()
        if not verify_tls:
            # Routers ship self-signed certs; verification is opt-in.
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        self._cookies = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cookies),
            urllib.request.HTTPSHandler(context=context),
        )
        self._opener.addheaders = [
            ("User-Agent", "LocalObserve-wifi-router-shipper/1.0"),
        ]
        self._form_token = ""
        self.logged_in = False

    def _get(self, path: str) -> str:
        request = urllib.request.Request(self.base_url + path)
        try:
            with self._opener.open(request, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", "replace")[:200]
            raise RouterError(f"GET {path} -> HTTP {err.code}: {body}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            raise RouterError(f"GET {path} failed: {err}") from None

    def _post(self, path: str, form: dict) -> str:
        data = urllib.parse.urlencode(form).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as err:
            raise err  # callers inspect code/body
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            raise RouterError(f"POST {path} failed: {err}") from None

    def _login_status(self) -> dict:
        try:
            payload = json.loads(self._get("/loginStatus.cgi"))
        except json.JSONDecodeError as err:
            raise RouterError(f"loginStatus.cgi returned non-JSON: {err}") from None
        if not isinstance(payload, dict):
            raise RouterError("loginStatus.cgi returned unexpected payload")
        return payload

    def login(self) -> None:
        """Establish an admin session (``sysauth`` cookie). Raises LoginError."""
        status = self._login_status()
        login_token = str(status.get("loginToken", ""))
        form = {
            "luci_username": encode_username(self.username),
            "luci_password": encode_password(self.password, login_token),
            "luci_view": "Desktop",
            "luci_token": login_token,
            "luci_keep_login": "0",
        }
        try:
            self._post("/login.cgi", form)
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", "replace")
            hint = self._flag_hint(body)
            raise LoginError(f"login rejected (HTTP {err.code}): {hint}") from None
        # Refresh the form token (used for logout) now that we have a session.
        self._form_token = str(self._login_status().get("token", ""))
        self.logged_in = True

    @staticmethod
    def _flag_hint(body: str) -> str:
        try:
            flag = json.loads(body).get("flag")
        except (json.JSONDecodeError, AttributeError):
            return "unparseable error response"
        return LOGIN_FLAG_HINTS.get(flag, f"unknown flag {flag}")

    def fetch_tab(self, tab: str) -> str:
        """Return the raw text of one log tab. Raises RouterError/LoginError."""
        try:
            return self._get(f"/log/messages_{tab}.log")
        except RouterError as err:
            # A 403 on a data fetch means the session lapsed; surface it as a
            # login error so the poll loop re-authenticates and retries.
            if "HTTP 403" in str(err) or "HTTP 401" in str(err):
                self.logged_in = False
                raise LoginError(f"session expired while fetching {tab}") from None
            raise

    def logout(self) -> None:
        """Best-effort logout: frees one of the router's 2 session slots."""
        if not self.logged_in:
            return
        try:
            self._post("/logout.cgi", {"token": self._form_token})
        except (RouterError, urllib.error.HTTPError) as err:
            LOG.warning("logout failed (session will expire on its own): %s", err)
        finally:
            self.logged_in = False
            self._cookies.clear()


# --------------------------------------------------------------------------
# Dedup state + JSONL output
# --------------------------------------------------------------------------

class ShipState:
    """Persisted dedup ring + per-tab content fingerprints.

    The state file is gzipped JSON (hash lists compress ~6x) and is rewritten
    only when dirty and at most every STATE_SAVE_INTERVAL_SECONDS to keep SSD
    churn low; callers force a final save on shutdown.
    """

    def __init__(self, path: Path, ring_size: int):
        self.path = path
        self.ring_size = ring_size
        self.emitted: deque[str] = deque(maxlen=ring_size)
        self._emitted_set: set[str] = set()
        self.tab_sha: dict[str, str] = {}
        self.dirty = False
        self._last_saved = 0.0
        self.load()

    def load(self) -> None:
        try:
            with gzip.open(self.path, "rt", encoding="utf-8") as fh:
                data = json.load(fh)
        except OSError:
            try:  # tolerate a legacy uncompressed state file
                data = json.loads(self.path.read_text())
            except (OSError, json.JSONDecodeError):
                return  # first run (or corrupt state) — start clean
        except json.JSONDecodeError:
            return
        if not isinstance(data, dict) or data.get("version") != STATE_VERSION:
            return
        for h in data.get("emitted", []):
            self._add(h)
        self.tab_sha = data.get("tab_sha", {})

    def _add(self, h: str) -> None:
        if len(self.emitted) == self.emitted.maxlen:
            evicted = self.emitted[0]
            self._emitted_set.discard(evicted)
        self.emitted.append(h)
        self._emitted_set.add(h)

    def seen(self, h: str) -> bool:
        return h in self._emitted_set

    def remember(self, h: str) -> None:
        if h not in self._emitted_set:
            self._add(h)

    def save(self) -> None:
        payload = {
            "version": STATE_VERSION,
            "emitted": list(self.emitted),
            "tab_sha": self.tab_sha,
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            json.dump(payload, fh)
        os.replace(tmp, self.path)
        self.dirty = False
        self._last_saved = time.monotonic()

    def save_if_due(self, force: bool = False) -> None:
        if not self.dirty:
            return
        if force or time.monotonic() - self._last_saved >= STATE_SAVE_INTERVAL_SECONDS:
            self.save()


def rotate_if_needed(path: Path, max_bytes: int) -> bool:
    """copytruncate-rotate the JSONL file once it exceeds ``max_bytes``.

    Matches the repository's logrotate contract (scripts/logrotate-localobserve.conf,
    validated by tests/test_stack_rotation.py): copy the active file to ``.1`` then
    truncate the active file in place, preserving its inode. The collector's filelog
    receiver holds an open descriptor on the active file; keeping the inode lets it
    detect the truncation (size shrink), reset its offset, and continue tailing new
    content without a gap. Renaming would change the inode and risk dropping the
    unread tail. The shipper is the sole writer and does not write during rotation
    (rotation runs after the append loop closes the file), so there is no
    write-between-copy-and-truncate loss window.
    """
    try:
        if path.stat().st_size <= max_bytes:
            return False
    except OSError:
        return False
    rotated = path.with_suffix(path.suffix + ".1")
    shutil.copyfile(path, rotated)
    with open(path, "r+") as fh:
        fh.truncate(0)
    LOG.info("rotated %s -> %s via copytruncate (>%d bytes)", path.name, rotated.name, max_bytes)
    return True


# --------------------------------------------------------------------------
# Shipper
# --------------------------------------------------------------------------

class WifiRouterShipper:
    def __init__(self, env: dict | None = None):
        env = env if env is not None else dict(os.environ)
        self.address = env.get("WIFI_ROUTER_ADDRESS", "").strip().rstrip("/")
        # Strip any SPA fragment the user may have pasted from the browser
        # address bar (e.g. ".../#/login").
        self.address = self.address.split("#", 1)[0].rstrip("/")
        self.username = env.get("WIFI_ROUTER_USERNAME", "").strip()
        self.password = env.get("WIFI_ROUTER_PASSWORD", "")
        self.verify_tls = env.get("WIFI_ROUTER_VERIFY_TLS", "false").strip().lower() in ("1", "true", "yes")
        self.poll_seconds = max(5, int(env.get("WIFI_ROUTER_POLL_SECONDS", DEFAULT_POLL_SECONDS)))
        self.tabs = tuple(
            t.strip().upper()
            for t in env.get("WIFI_ROUTER_TABS", ",".join(DEFAULT_TABS)).split(",")
            if t.strip()
        ) or DEFAULT_TABS
        self.output_dir = Path(env.get("OUTPUT_DIR", DEFAULT_OUTPUT_DIR))
        self.max_output_bytes = int(env.get("WIFI_ROUTER_MAX_OUTPUT_BYTES", DEFAULT_MAX_OUTPUT_BYTES))
        self.max_records_per_poll = int(env.get("WIFI_ROUTER_MAX_RECORDS_PER_POLL", DEFAULT_MAX_RECORDS_PER_POLL))
        self.state = ShipState(
            self.output_dir / STATE_FILENAME,
            int(env.get("WIFI_ROUTER_STATE_RING", DEFAULT_RING_SIZE)),
        )
        self.client: FiosClient | None = None
        self._stop = False

    @property
    def configured(self) -> bool:
        return bool(self.address and self.username and self.password)

    def stop(self, *_args) -> None:
        self._stop = True

    def _ensure_client(self) -> FiosClient:
        if self.client is None:
            self.client = FiosClient(
                self.address, self.username, self.password,
                verify_tls=self.verify_tls,
            )
        return self.client

    def poll_once(self) -> int:
        """One fetch cycle. Returns the number of newly emitted records.

        Emission is budgeted (max_records_per_poll) so a large backfill ramps
        over several polls instead of bursting the collector's memory_limiter.
        A tab's content fingerprint is stored only once the tab is fully
        processed, so an interrupted tab resumes from the dedup ring on the
        next poll without re-emitting lines.
        """
        client = self._ensure_client()
        if not client.logged_in:
            client.login()  # raises LoginError / RouterError
        emitted = 0
        budget = self.max_records_per_poll
        observed_time = datetime.now(timezone.utc).isoformat(timespec="seconds")
        output_path = self.output_dir / OUTPUT_FILENAME
        try:
            for tab in self.tabs:
                if budget <= 0:
                    break
                content = client.fetch_tab(tab)
                content_sha = hashlib.sha256(content.encode("utf-8", "replace")).hexdigest()
                if self.state.tab_sha.get(tab) == content_sha:
                    continue  # tab unchanged since last poll
                new_here = 0
                truncated = False
                with output_path.open("a", encoding="utf-8") as out:
                    for raw in content.splitlines():
                        raw = raw.strip()
                        if not raw:
                            continue
                        h = line_hash(raw)
                        if self.state.seen(h):
                            continue
                        if budget <= 0:
                            truncated = True
                            break
                        record = parse_line(raw, tab, observed_time)
                        out.write(json.dumps(record, ensure_ascii=False) + "\n")
                        self.state.remember(h)
                        self.state.dirty = True
                        new_here += 1
                        budget -= 1
                if truncated:
                    LOG.info("tab %s: emission budget exhausted; resuming next poll", tab)
                else:
                    self.state.tab_sha[tab] = content_sha
                emitted += new_here
                if new_here:
                    LOG.info("tab %s: +%d new record(s)", tab, new_here)
        finally:
            client.logout()
        if emitted:
            rotate_if_needed(output_path, self.max_output_bytes)
        self.state.save_if_due()
        return emitted

    def run(self) -> None:
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if not self.configured:
            LOG.warning(
                "WIFI_ROUTER_ADDRESS/USERNAME/PASSWORD not set — idling. "
                "Set them in .env and restart this container to enable router log ingestion."
            )
            while not self._stop:
                time.sleep(300)
            return

        LOG.info("shipping router logs from %s (tabs: %s, poll: %ds)",
                 self.address, ",".join(self.tabs), self.poll_seconds)
        try:
            while not self._stop:
                start = time.monotonic()
                try:
                    emitted = self.poll_once()
                    if emitted:
                        LOG.info("poll complete: %d record(s) appended to %s",
                                 emitted, OUTPUT_FILENAME)
                except LoginError as err:
                    LOG.error("router login problem: %s", err)
                except RouterError as err:
                    LOG.warning("router unreachable this cycle: %s", err)
                except Exception:  # noqa: BLE001 — a shipper must never crash the loop
                    LOG.exception("unexpected poll error")
                elapsed = time.monotonic() - start
                remaining = max(1.0, self.poll_seconds - elapsed)
                deadline = time.monotonic() + remaining
                while not self._stop and time.monotonic() < deadline:
                    time.sleep(min(1.0, deadline - time.monotonic()))
        finally:
            # Persist the dedup ring so a restart does not re-emit history.
            self.state.save_if_due(force=True)


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    WifiRouterShipper().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
