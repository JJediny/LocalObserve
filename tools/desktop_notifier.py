#!/usr/bin/env python3
"""
desktop_notifier.py - LocalObserve Host-Side Desktop Alerting Daemon
Watches the local .data/alerts directory for security alerts and triggers native notifications.
"""
import os
import sys
import time
import json
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
        "sound": "bell"
    },
    "high": {
        "urgency": "critical",
        "icon": "security-high",
        "title_prefix": "⚠️ High Alert: ",
        "sound": "message-new-instant"
    },
    "normal": {
        "urgency": "normal",
        "icon": "security-medium",
        "title_prefix": "Security Event: ",
        "sound": "message-new-instant"
    },
    "low": {
        "urgency": "low",
        "icon": "security-low",
        "title_prefix": "Security Info: ",
        "sound": None
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

def send_notification(alert):
    """Trigger the native host notify-send command."""
    alert_name = alert.get("alert_name", "Unknown Security Event")
    description = alert.get("description", "No details provided.")
    severity = alert.get("severity", "normal").lower()
    
    style = SEVERITY_STYLES.get(severity, SEVERITY_STYLES["normal"])
    title = f"{style['title_prefix']}{alert_name}"
    
    cmd = [
        "notify-send",
        "--urgency", style["urgency"],
        "--icon", style["icon"],
        "--category", "transfer.error",
        title,
        description
    ]
    
    try:
        subprocess.run(cmd, check=True)
        play_alert_sound(style["sound"])
    except FileNotFoundError:
        print("Error: 'notify-send' is not installed or available on this system.", file=sys.stderr)

def main():
    print(f"[*] LocalObserve Desktop Notifier watching: {ALERT_DIR}")
    ALERT_DIR.mkdir(parents=True, exist_ok=True)
    
    seen_files = set(ALERT_DIR.glob("*.json"))
    
    while True:
        try:
            current_files = set(ALERT_DIR.glob("*.json"))
            new_files = current_files - seen_files
            
            for file_path in new_files:
                if not file_path.exists():
                    continue
                try:
                    time.sleep(0.1)
                    alert_data = json.loads(file_path.read_text(encoding="utf-8"))
                    send_notification(alert_data)
                    file_path.unlink()
                except Exception as e:
                    print(f"[!] Error processing {file_path.name}: {e}", file=sys.stderr)
            
            seen_files = current_files - {f for f in new_files if not f.exists()}
            time.sleep(1)
        except KeyboardInterrupt:
            print("\n[*] Exiting notifier daemon.")
            break

if __name__ == "__main__":
    main()
