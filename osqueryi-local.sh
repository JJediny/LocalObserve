#!/bin/bash
# Run an interactive osquery shell without reusing the daemon logging config.
# This avoids pack-loading and filesystem-logger errors when using osqueryi as a normal user.

set -e

exec /usr/bin/osqueryi \
  --config_path /dev/null \
  --disable_events=true \
  --disable_logging=true \
  --database_path /tmp/osqueryi-local.db \
  "$@"
