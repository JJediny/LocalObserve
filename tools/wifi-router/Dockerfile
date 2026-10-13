# wifi-router-shipper — polls the router's web admin API and writes JSONL for
# the otel-collector's file_log/router receiver. Stdlib-only Python: no pip
# install step, which keeps the image minimal and the CVE surface to the base.
#
# Pinned base (python:3.13-alpine, digest of 2026-10-12); re-pin via the
# weekly Container Image Scan workflow, see docs/container_security_scan.md.
FROM python:3.13-alpine@sha256:2d9aefe2fef018a7eb2c13064c89c71929800fd2e5dccdbf52ea5da5bb8d929a

COPY wifi_router_shipper.py /usr/local/bin/wifi_router_shipper.py

# JSONL output + dedup state land here; compose bind-mounts .data/wifi-router.
RUN mkdir -p /var/log/wifi-router

ENTRYPOINT ["python3", "/usr/local/bin/wifi_router_shipper.py"]
