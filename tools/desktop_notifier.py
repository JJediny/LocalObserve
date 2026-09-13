#!/usr/bin/env python3
"""
desktop_notifier.py - LocalObserve Host-Side Desktop Alerting Daemon
Watches the local .data/alerts directory for security alerts and triggers native notifications.
"""
import os
import sys
import time
import json
import re
import subprocess
from pathlib import Path

# Paths
REPO_ROOT = Path(__file__).resolve().parents[1]
ALERT_DIR = REPO_ROOT / ".data" / "alerts"

# Severity Styling
SEVERITY_STYLES = {
    "critical": {
        "urgency": "critical",
        "icon": "dialog-error",
        "title_prefix": "🚨 CRITICAL SECURITY ALERT: ",
        "sound": "bell",
        "expire_time": 8000
    },
    "high": {
        "urgency": "normal",
        "icon": "security-high",
        "title_prefix": "⚠️ High Alert: ",
        "sound": "message-new-instant",
        "expire_time": 5000
    },
    "normal": {
        "urgency": "normal",
        "icon": "security-medium",
        "title_prefix": "Security Event: ",
        "sound": "message-new-instant",
        "expire_time": 4000
    },
    "low": {
        "urgency": "low",
        "icon": "security-low",
        "title_prefix": "Security Info: ",
        "sound": None,
        "expire_time": 3000
    }
}

def play_alert_sound(sound_name):
    """Play alert sound if audio utilities exist on host."""
    if not sound_name:
        return
    for cmd in [
        ["paplay", f"/usr/share/sounds/freedesktop/stereo/{sound_name}.oga"],
        ["aplay", f"/usr/share/sounds/freedesktop/stereo/{sound_name}.wav"]
    ]:
        if Path(cmd[1]).exists():
            try:
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                break
            except OSError:
                pass

def send_notification(alert, expire_override=None):
    """Trigger the native host notify-send command with explicit expiration timeout."""
    alert_name = alert.get("alert_name", "Unknown Security Event")
    description = alert.get("description", "No details provided.")
    severity = alert.get("severity", "normal").lower()

    style = SEVERITY_STYLES.get(severity, SEVERITY_STYLES["normal"])
    title = f"{style['title_prefix']}{alert_name}"
    expire_time = str(expire_override or os.environ.get("NOTIFY_EXPIRE_TIME", style["expire_time"]))

    cmd = [
        "notify-send",
        "--urgency", style["urgency"],
        "--icon", style["icon"],
        "--expire-time", expire_time,
        "--category", "transfer.error",
        title,
        description
    ]

    try:
        subprocess.run(cmd, check=True)
        play_alert_sound(style["sound"])
    except FileNotFoundError:
        print("Error: 'notify-send' is not installed or available on this system.", file=sys.stderr)

def dismiss_notifications():
    """Clear stuck desktop notifications across common Linux notification daemons."""
    print("[*] Dismissing active desktop notifications...")
    for cmd in [
        ["dunstctl", "close-all"],
        ["killall", "notify-osd"],
        ["killall", "xfce4-notifyd"]
    ]:
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except OSError:
            pass

def main():
    if "--dismiss" in sys.argv:
        dismiss_notifications()
        return

    replay = "--replay" in sys.argv or "--all" in sys.argv
    once = "--once" in sys.argv

    print(f"[*] LocalObserve Desktop Notifier watching: {ALERT_DIR}")
    if replay:
        print("[*] Replay mode enabled: processing existing alert backlog...")
    ALERT_DIR.mkdir(parents=True, exist_ok=True)

    seen_files = set() if replay else set(ALERT_DIR.glob("*.json"))

    while True:
        try:
            current_files = set(ALERT_DIR.glob("*.json"))
            new_files = current_files - seen_files

            for file_path in sorted(new_files):
                if not file_path.exists():
                    continue
                try:
                    time.sleep(0.05)
                    raw_text = file_path.read_text(encoding="utf-8", errors="replace")
                    try:
                        alert_data = json.loads(raw_text, strict=False)
                    except json.JSONDecodeError:
                        # Fallback for unescaped template values
                        cleaned = re.sub(r'[\x00-\x1f]', '', raw_text)
                        alert_data = json.loads(cleaned, strict=False)
                    send_notification(alert_data)
                    file_path.unlink()
                except Exception as e:
                    print(f"[!] Error processing {file_path.name}: {e}", file=sys.stderr)
                    file_path.unlink(missing_ok=True)

            seen_files = current_files - {f for f in new_files if not f.exists()}

            if once:
                print(f"[+] Replay complete. Processed {len(new_files)} alerts.")
                break

            time.sleep(1)
        except KeyboardInterrupt:
            print("\n[*] Exiting notifier daemon.")
            break

if __name__ == "__main__":
    main()
