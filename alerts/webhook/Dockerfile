# Keep the upstream webhook binary in a build stage, but do not inherit its
# mutable runtime base. The final image uses a pinned Alpine base so release
# scans and rebuilds are reproducible.
FROM almir/webhook@sha256:f77cc91c91d1527b48052280af38b50791e842ad8dd291e9b360a0c13c9ca991 AS webhook

FROM alpine@sha256:fd791d74b68913cbb027c6546007b3f0d3bc45125f797758156952bc2d6daf40

# Install libnotify (provides notify-send), dbus tools, curl, and xhost for X11 access
USER root
RUN apk add --no-cache libnotify dbus dbus-x11 curl xhost
COPY --from=webhook /usr/local/bin/webhook /usr/local/bin/webhook

# Create machine-id so dbus can connect to host session bus
RUN mkdir -p /var/lib/dbus

# Copy our hook definitions and notification script
COPY hooks.json /etc/webhook/hooks.json
COPY notify.sh /hooks/notify.sh
RUN chmod +x /hooks/notify.sh

EXPOSE 9000

ENTRYPOINT ["/usr/local/bin/webhook", "-hooks", "/etc/webhook/hooks.json", "-verbose", "-port", "9000"]
