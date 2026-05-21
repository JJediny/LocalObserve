#!/usr/bin/env bash
# oo-alerts.sh: Export/import OpenObserve alert definitions for GitOps
export_alerts() { echo 'TODO: implement OpenObserve alert export via OO REST API'; }
import_alerts() { echo 'TODO: implement OpenObserve alert import via OO REST API'; }
case "$1" in export) export_alerts;; import) import_alerts;; *) echo 'Usage: oo-alerts.sh export|import'; exit 1;; esac
