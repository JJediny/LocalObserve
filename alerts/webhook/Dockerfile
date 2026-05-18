FROM almir/webhook:latest

# Install libnotify (provides notify-send) and dbus tools
USER root
RUN apk add --no-cache libnotify dbus dbus-x11

# Copy our hook definitions and notification script
COPY hooks.json /etc/webhook/hooks.json
COPY notify.sh /hooks/notify.sh
RUN chmod +x /hooks/notify.sh

EXPOSE 9000

ENTRYPOINT ["/usr/local/bin/webhook", "-hooks", "/etc/webhook/hooks.json", "-verbose", "-port", "9000"]
