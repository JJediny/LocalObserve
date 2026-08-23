#!/usr/bin/env python3
"""
sync_threat_intel.py — pull lightweight threat-intel feeds into shared volumes.

Fetches Tor/VPN IPs, bad User-Agents, Windows named pipes, and ransomware
extensions from `mthcht/awesome-lists` and writes them (plus Falco/osquery
consumption fragments) into an output directory that is bind-mounted into the
LocalObserve stack.

Offline-safe: the last successful fetch is cached. On network failure the cache
is reused (or empty-but-valid stubs are written) and the process still exits 0 so
the pipeline can boot. Feed URLs/paths are best-effort defaults for
mthcht/awesome-lists and can be overridden per source with `--source-url KEY=URL`.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.request
from pathlib import Path

import yaml

LOGGER = logging.getLogger("sync_threat_intel")

DEFAULT_BASE = "https://raw.githubusercontent.com/mthcht/awesome-lists/main"
DEFAULT_OUTPUT = ".data/threat-intel"
DEFAULT_MOUNT_DIR = "/var/lib/threat-intel"

# Relative paths under DEFAULT_BASE. Override per-source with --source-url KEY=URL.
DEFAULT_SOURCES: dict[str, str] = {
    "tor_ips": "ips/tor_exit_nodes.txt",
    "bad_user_agents": "user_agents/bad_user_agents.txt",
    "named_pipes": "named_pipes/windows_named_pipes.txt",
    "ransomware_extensions": "extensions/ransomware_extensions.txt",
}

# Per-source normalization applied after fetching raw lines.
NORMALIZERS = {
    "ransomware_extensions": lambda items: sorted(
        {i.lower().lstrip(".") for i in items}
    ),
}

# Maps a source key to the Falco list name it populates in the generated fragment.
KEY_TO_FALCO_LIST = {
    "tor_ips": "threat_intel_tor_ips",
    "bad_user_agents": "threat_intel_bad_user_agents",
    "named_pipes": "threat_intel_named_pipes",
    "ransomware_extensions": "threat_intel_ransomware_extensions",
}


def parse_lines(raw: str) -> list[str]:
    """Strip comments/blank lines and surrounding whitespace from raw feed text."""
    out: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


def fetch(url: str, timeout: int = 20) -> list[str]:
    """Download a feed URL and return its cleaned, non-empty lines."""
    req = urllib.request.Request(
        url, headers={"User-Agent": "localobserve-sync/1.0"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")
    return parse_lines(raw)


def build_source_urls(base: str, overrides: dict[str, str]) -> dict[str, str]:
    return {
        key: overrides.get(key, f"{base.rstrip('/')}/{rel.lstrip('/')}")
        for key, rel in DEFAULT_SOURCES.items()
    }


def render_falco_fragment(data: dict[str, list[str]]) -> str:
    """Render a Falco rules fragment: one `list` per source with its items."""
    fragment: list[dict] = []
    for key, list_name in KEY_TO_FALCO_LIST.items():
        fragment.append(
            {
                "list": list_name,
                "items": data.get(key, []),
                "override": {"items": "append"},
            }
        )
    return yaml.safe_dump(fragment, sort_keys=False)


def render_osquery_fragment(mount_dir: str) -> dict:
    """Render an osquery config fragment exposing the feeds via file_paths FIM."""
    return {
        "file_paths": {
            "threat_intel": [f"{mount_dir}/{key}.txt" for key in DEFAULT_SOURCES]
        }
    }


def collect(base: str, overrides: dict[str, str], out: Path, no_cache: bool) -> dict[str, list[str]]:
    """Fetch every source, falling back to cache; return the merged dataset."""
    urls = build_source_urls(base, overrides)
    data: dict[str, list[str]] = {}
    any_failure = False
    for key, url in urls.items():
        cache_file = out / f"{key}.cache"
        try:
            items = fetch(url)
            normalizer = NORMALIZERS.get(key)
            if normalizer:
                items = normalizer(items)
            (out / f"{key}.txt").write_text("\n".join(items) + "\n")
            cache_file.write_text("\n".join(items) + "\n")
            data[key] = items
            LOGGER.info("fetched %s (%d items)", key, len(items))
        except Exception as exc:  # noqa: BLE001 — offline-safe by design
            LOGGER.warning("fetch failed for %s: %s", key, exc)
            any_failure = True
            if not no_cache and cache_file.exists():
                cached = parse_lines(cache_file.read_text())
                normalizer = NORMALIZERS.get(key)
                if normalizer:
                    cached = normalizer(cached)
                LOGGER.info("using cached %s (%d items)", key, len(cached))
                data[key] = cached
            else:
                LOGGER.warning("no cache for %s; writing empty stub", key)
                (out / f"{key}.txt").write_text("")
                data[key] = []
    if any_failure and not any(data.values()):
        LOGGER.error("all sources failed and no cache available; wrote empty stubs")
    return data


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT)
    parser.add_argument("--base-url", default=DEFAULT_BASE,
                        help="Base URL for mthcht/awesome-lists raw files.")
    parser.add_argument("--mount-dir", default=DEFAULT_MOUNT_DIR,
                        help="In-container path the output dir is mounted at.")
    parser.add_argument("--source-url", action="append", default=[],
                        metavar="KEY=URL",
                        help="Override a single source URL (repeatable).")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--no-cache", action="store_true",
                        help="Ignore the on-disk cache on failure.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Log intended fetches without writing files.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    overrides = {}
    for item in args.source_url:
        if "=" not in item:
            LOGGER.error("invalid --source-url %r (expected KEY=URL)", item)
            return 2
        k, v = item.split("=", 1)
        overrides[k.strip()] = v.strip()

    out = Path(args.output_dir)
    urls = build_source_urls(args.base_url, overrides)
    if args.dry_run:
        for key, url in urls.items():
            LOGGER.info("[dry-run] would fetch %s -> %s", key, url)
        return 0

    out.mkdir(parents=True, exist_ok=True)
    data = collect(args.base_url, overrides, out, args.no_cache)

    (out / "threat_intel.json").write_text(json.dumps(data, indent=2))
    (out / "falco_rules.threat_intel.local.yaml").write_text(
        render_falco_fragment(data)
    )
    (out / "osquery.threat_intel.conf").write_text(
        json.dumps(render_osquery_fragment(args.mount_dir), indent=2)
    )
    LOGGER.info("wrote threat-intel artifacts to %s", out)
    return 0


if __name__ == "__main__":
    sys.exit(run())
