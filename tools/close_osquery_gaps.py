import json
import os

CONF_PATH = '/home/john/LocalObserve/osqueryd.conf'

with open(CONF_PATH, 'r') as f:
    conf = json.load(f)

# Add file_paths for FIM
if 'file_paths' not in conf:
    conf['file_paths'] = {}

conf['file_paths']['bash_profiles'] = [
    "/home/%/.bashrc",
    "/home/%/.bash_profile",
    "/home/%/.bash_history",
    "/root/.bashrc",
    "/root/.bash_profile",
    "/root/.bash_history"
]
conf['file_paths']['init_scripts'] = [
    "/etc/rc.local",
    "/etc/init.d/%%"
]

# Add file_events query to schedule
if 'file_events' not in conf['schedule']:
    conf['schedule']['file_events'] = {
        "query": "SELECT * FROM file_events;",
        "interval": 300,
        "description": "FIM events for profile and init scripts [T1546.004] [T1037.004] [T1070.003]",
        "removed": False
    }

with open(CONF_PATH, 'w') as f:
    json.dump(conf, f, indent=2)

print("[*] Successfully closed OSQuery gaps.")
