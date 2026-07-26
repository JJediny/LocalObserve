import os
import time
import json
import requests
from pathlib import Path

HOOK_ID = "test-alert"
BASE_URL = os.environ.get("ALERT_RECEIVER_URL", "http://localhost:9000")
ALERT_DIR = Path(".data/alerts")

falco_payload = {
    "rule": "TestRule",
    "priority": "High",
    "output": "This is a synthetic falco test alert",
    "source": "falco"
}


def wait_for_stack(timeout=60):
    start = time.time()
    url = BASE_URL
    while time.time() - start < timeout:
        try:
            r = requests.get(url, timeout=2)
            # The root or a nonexistent hook returns 404, which proves the server is reachable and active
            if r.status_code == 404 or r.status_code >= 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(1)
    return False


def test_falco_payload_processing():
    # Ensure alert dir exists
    ALERT_DIR.mkdir(parents=True, exist_ok=True)

    assert wait_for_stack(), "Alert receiver did not become reachable in time"

    # Capture the files existing BEFORE we trigger the webhook
    existing_files = set(ALERT_DIR.glob("*.json"))

    url = f"{BASE_URL}/hooks/{HOOK_ID}"
    headers = {"Content-Type": "application/json", "X-Alert-Source": "localobserve"}

    start = time.time()
    r = requests.post(url, headers=headers, json=falco_payload, timeout=5)
    assert r.status_code == 200, f"Unexpected response: {r.status_code} {r.text}"

    # Wait for a new alert file to appear (polling newest files not in existing_files)
    deadline = time.time() + 10
    newest = None
    while time.time() < deadline:
        current_files = set(ALERT_DIR.glob("*.json"))
        new_files = current_files - existing_files
        if new_files:
            # choose the most recently modified new file
            sorted_new = sorted(list(new_files), key=lambda p: p.stat().st_mtime, reverse=True)
            candidate = sorted_new[0]
            if candidate.stat().st_mtime >= start - 1:
                newest = candidate
                break
        time.sleep(0.5)

    assert newest is not None, "No alert file created by alert-receiver"

    data = json.loads(newest.read_text(encoding="utf-8"))
    assert "alert_name" in data
    assert "description" in data
    assert "This is a synthetic falco test alert" in data.get("description", ""), (
        f"Unexpected description: {data.get('description')!r} in {newest}"
    )

    # cleanup the alert file created by this test
    try:
        newest.unlink()
    except OSError:
        pass


def test_rsigma_payload_processing():
    # Ensure alert dir exists
    ALERT_DIR.mkdir(parents=True, exist_ok=True)

    assert wait_for_stack(), "Alert receiver did not become reachable in time"

    # Capture the files existing BEFORE we trigger the webhook
    existing_files = set(ALERT_DIR.glob("*.json"))

    url = f"{BASE_URL}/hooks/security-alert-open"
    headers = {"Content-Type": "application/json"}
    rsigma_payload = {
        "alert_name": "Suspicious Namespace Unshare Command",
        "severity": "high",
        "description": "Rule ID: 718c5dbc-b1a3-419b-a329-e7721d294257 triggered. Tags: ['attack.t1059', 'attack.t1071']"
    }

    start = time.time()
    r = requests.post(url, headers=headers, json=rsigma_payload, timeout=5)
    assert r.status_code == 200, f"Unexpected response: {r.status_code} {r.text}"

    # Wait for a new alert file to appear
    deadline = time.time() + 10
    newest = None
    while time.time() < deadline:
        current_files = set(ALERT_DIR.glob("*.json"))
        new_files = current_files - existing_files
        if new_files:
            sorted_new = sorted(list(new_files), key=lambda p: p.stat().st_mtime, reverse=True)
            candidate = sorted_new[0]
            if candidate.stat().st_mtime >= start - 1:
                newest = candidate
                break
        time.sleep(0.5)

    assert newest is not None, "No alert file created by alert-receiver for RSigma"

    data = json.loads(newest.read_text(encoding="utf-8"))
    assert data.get("alert_name") == "Suspicious Namespace Unshare Command"
    assert data.get("severity") == "high"
    assert "Rule ID: 718c5dbc-b1a3-419b-a329-e7721d294257" in data.get("description", "")

    # cleanup the alert file created by this test
    try:
        newest.unlink()
    except OSError:
        pass
