#!/usr/bin/env bash
# Runs on the server as root, called by .github/workflows/bot.yml after the code was copied to /opt/proxybot/app.
# Safe to run again: it only installs what's missing, then restarts the bot.
set -euo pipefail

APP=/opt/proxybot/app
VENV=/opt/proxybot/venv

if ! python3 -c 'import venv, ensurepip' 2>/dev/null; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq python3 python3-venv >/dev/null
fi
python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' || { echo "Python 3.9+ needed" >&2; exit 1; }

id proxybot >/dev/null 2>&1 || useradd --system --home-dir /opt/proxybot --shell /usr/sbin/nologin proxybot
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --disable-pip-version-check -r "$APP/requirements.txt"

chown -R root:root "$APP"
chmod 600 /etc/proxybot.env
install -m 644 "$APP/deploy/proxybot.service" /etc/systemd/system/proxybot.service
systemctl daemon-reload
systemctl enable -q proxybot
systemctl restart proxybot

# give it a moment to log in; a bad token or a crash shows up here instead of silently later
sleep 8
if ! systemctl is-active -q proxybot; then
  journalctl -u proxybot -n 40 --no-pager >&2
  exit 1
fi
journalctl -u proxybot -n 5 --no-pager
