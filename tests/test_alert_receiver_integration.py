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
    url = f"{BASE_URL}/hooks/{HOOK_ID}"
    while time.time() - start < timeout:
        try:
            r = requests.get(url, timeout=2)
            # The webhook returns 405 for GETs typically; any response implies service up
            if r.status_code >= 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(1)
    return False


def test_falco_payload_processing(tmp_path):
    # Ensure alert dir exists and is empty
    ALERT_DIR.mkdir(parents=True, exist_ok=True)
    # clean existing files
    before = set(ALERT_DIR.glob("*.json"))

    assert wait_for_stack(), "Alert receiver did not become reachable in time"

    url = f"{BASE_URL}/hooks/{HOOK_ID}"
    headers = {"Content-Type": "application/json", "X-Alert-Source": "localobserve"}
    r = requests.post(url, headers=headers, json=falco_payload, timeout=5)
    assert r.status_code == 200, f"Unexpected response: {r.status_code} {r.text}"

    # Give the webhook container a moment to write files
    time.sleep(1)

    after = set(ALERT_DIR.glob("*.json"))
    new = after - before
    assert len(new) == 1, f"Expected one new alert file, found {len(new)}"

    # verify contents
    p = new.pop()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "alert_name" in data
    assert "description" in data
    assert "This is a synthetic falco test alert" in data.get("description", "")

    # cleanup
    p.unlink()
