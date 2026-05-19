FROM almir/webhook:latest

# Install libnotify (provides notify-send), dbus tools, curl, and xhost for X11 access
USER root
RUN apk add --no-cache libnotify dbus dbus-x11 curl xhost

# Create machine-id so dbus can connect to host session bus
RUN mkdir -p /var/lib/dbus

# Copy our hook definitions and notification script
COPY hooks.json /etc/webhook/hooks.json
COPY notify.sh /hooks/notify.sh
RUN chmod +x /hooks/notify.sh

EXPOSE 9000

ENTRYPOINT ["/usr/local/bin/webhook", "-hooks", "/etc/webhook/hooks.json", "-verbose", "-port", "9000"]
