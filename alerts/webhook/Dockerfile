# Multi-stage build: compile upstream adnanh/webhook from source with modern Go compiler
# to eliminate legacy Go standard library CVEs.
FROM golang:alpine AS builder
RUN go install github.com/adnanh/webhook@v2.8.3

# Pinned Alpine runtime base: 0 CRITICAL, 0 HIGH
FROM alpine@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b

# Install libnotify (provides notify-send), dbus tools, curl, and xhost for X11 access
USER root
RUN apk update && apk upgrade --no-cache && apk add --no-cache libnotify dbus dbus-x11 curl xhost
COPY --from=builder /go/bin/webhook /usr/local/bin/webhook

# Create machine-id so dbus can connect to host session bus
RUN mkdir -p /var/lib/dbus /etc/webhook /hooks

# Copy hook definitions and notification script
COPY hooks.json /etc/webhook/hooks.json
COPY notify.sh /hooks/notify.sh
RUN chmod +x /hooks/notify.sh

EXPOSE 9000

ENTRYPOINT ["/usr/local/bin/webhook", "-hooks", "/etc/webhook/hooks.json", "-verbose", "-port", "9000"]
