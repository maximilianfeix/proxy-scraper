#!/bin/sh
# Runs on the server as root, called by .github/workflows/bot.yml after the bot was unpacked into a fresh
# /opt/proxybot/releases/<id>.
#
#   sh install.sh /opt/proxybot/releases/<id>   install that release and switch to it
#   sh install.sh --rollback                     go back to the release before (by hand)
#
# Every release gets its own venv, installed with --require-hashes from requirements.lock – the versions the
# bot's CI tested. Only when that venv imports the bot does /opt/proxybot/current point at it; the release
# before stays as /opt/proxybot/previous, venv and all, so going back never depends on what the new release
# installed. If the bot doesn't log in after the restart, current goes back to the previous release by itself.
#
# "Comes up" means ready, not just running: once every configured bot has logged in (Discord on_ready, Telegram
# getMe), the bot writes its PID to PROXYBOT_READY_FILE. A release counts only when that file holds the PID systemd
# started and the same process still runs SETTLE seconds later. A refused token makes the bot exit instead of
# retrying, so systemd restarts it with a new PID and it never gets there.
set -eu

BASE=${PROXYBOT_BASE:-/opt/proxybot}
UNIT_DIR=${PROXYBOT_UNIT_DIR:-/etc/systemd/system}
ENV_FILE=${PROXYBOT_ENV_FILE:-/etc/proxybot.env}
READY_FILE=${PROXYBOT_READY_FILE:-/run/proxybot/ready}  # must match Environment= in deploy/proxybot.service
READY_TIMEOUT=${PROXYBOT_READY_TIMEOUT:-90}  # seconds the bot gets to log in everywhere
SETTLE=${PROXYBOT_SETTLE:-15}  # seconds the ready process must keep running (longer than RestartSec=10)
KEEP=${PROXYBOT_KEEP:-3}       # releases kept on disk (current and previous always are)

fail() {
  printf '%s\n' "$*" >&2
  exit 1
}

# where a symlink points, empty if there is none
target() {
  if [ -L "$1" ]; then readlink "$1"; fi
}

point() {
  ln -sfn "$2" "$1"
}

# the PID of the running bot, empty if it doesn't run
main_pid() {
  pid=$(systemctl show -p MainPID --value proxybot 2>/dev/null) || pid=
  [ "$pid" != 0 ] && printf '%s' "$pid"
  return 0
}

# the bot runs and the process systemd started is the one that wrote the ready file (not a stale one)
ready() {
  systemctl is-active -q proxybot || return 1
  pid=$(main_pid)
  [ -n "$pid" ] && [ -f "$READY_FILE" ] && [ "$(cat "$READY_FILE" 2>/dev/null)" = "$pid" ]
}

# install the unit of release $1, restart and wait until the bot has logged in and stays up
activate() {
  install -m 644 "$1/deploy/proxybot.service" "$UNIT_DIR/proxybot.service" || return 1
  systemctl daemon-reload || return 1
  systemctl enable -q proxybot || return 1
  systemctl restart proxybot || return 1
  if ! grep -q PROXYBOT_READY_FILE "$1/deploy/proxybot.service"; then
    # a release from before the ready file (going back to it): all it can tell is whether it runs
    sleep "$SETTLE"
    systemctl is-active -q proxybot
    return
  fi
  waited=0
  until ready; do
    if [ "$waited" -ge "$READY_TIMEOUT" ]; then
      echo "the bot did not log in within $READY_TIMEOUT s" >&2
      return 1
    fi
    sleep 1
    waited=$((waited + 1))
  done
  started=$(main_pid)
  sleep "$SETTLE"
  if ! ready || [ "$(main_pid)" != "$started" ]; then
    echo "the bot stopped again after logging in" >&2
    return 1
  fi
}

# This output ends up in the log of a public repository: on failure show the bot's own lines without the
# server's host name (-o cat). The journal on the server has the rest.
show_log() {
  journalctl -u proxybot -n 40 --no-pager -o cat >&2 || true
}

# delete the oldest releases beyond KEEP, never the current or the previous one
prune() {
  cur=$(target "$BASE/current")
  prev=$(target "$BASE/previous")
  total=0
  for dir in "$BASE"/releases/*/; do
    [ -d "$dir" ] && total=$((total + 1))
  done
  excess=$((total - KEEP))
  for dir in "$BASE"/releases/*/; do  # oldest first: release ids start with the UTC time
    [ "$excess" -gt 0 ] || break
    dir=${dir%/}
    if [ "$dir" != "$cur" ] && [ "$dir" != "$prev" ]; then
      rm -rf "$dir"
      excess=$((excess - 1))  # only what was removed counts: skipping current/previous frees nothing
    fi
  done
}

rollback() {
  cur=$(target "$BASE/current")
  prev=$(target "$BASE/previous")
  if [ -z "$prev" ] || [ ! -d "$prev" ]; then
    fail "no previous release to go back to (releases are in $BASE/releases)"
  fi
  point "$BASE/current" "$prev"
  if [ -n "$cur" ]; then point "$BASE/previous" "$cur"; fi
  if ! activate "$prev"; then
    show_log
    fail "the previous release $(basename "$prev") does not come up either"
  fi
  echo "proxybot is running $(basename "$prev") again (rolled back from $(basename "${cur:-none}"))"
}

case "${1:-}" in
  --rollback)
    rollback
    exit 0
    ;;
  "")
    fail "usage: install.sh $BASE/releases/<id> | install.sh --rollback"
    ;;
esac

REL=${1%/}
case "$REL" in
  "$BASE"/releases/*/*) fail "not a release directory: $REL" ;;
  "$BASE"/releases/?*) ;;
  *) fail "not under $BASE/releases: $REL" ;;
esac
[ -f "$REL/requirements.lock" ] || fail "$REL has no requirements.lock"

if ! python3 -c 'import venv, ensurepip' 2>/dev/null; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq python3 python3-venv >/dev/null
fi
python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' || fail "Python 3.9+ needed"

id proxybot >/dev/null 2>&1 || useradd --system --home-dir "$BASE" --shell /usr/sbin/nologin proxybot

# a fresh venv for this release, exactly the tested versions, every file checked against its hash
rm -rf "$REL/venv"
python3 -m venv "$REL/venv"
"$REL/venv/bin/pip" install -q --disable-pip-version-check --require-hashes -r "$REL/requirements.lock"
# a missing dependency or a broken module stops here – before the running bot is touched
(cd "$REL" && "$REL/venv/bin/python" -c 'import proxybot.__main__') \
  || fail "release $(basename "$REL") does not import – nothing was switched, the bot keeps running as before"

chown -R root:root "$REL"
chmod 600 "$ENV_FILE"

old=$(target "$BASE/current")
point "$BASE/current" "$REL"
if activate "$REL"; then
  if [ -n "$old" ] && [ "$old" != "$REL" ]; then point "$BASE/previous" "$old"; fi
  prune
  echo "proxybot is running ($(basename "$REL"))"
  exit 0
fi

show_log
if [ -n "$old" ] && [ "$old" != "$REL" ] && [ -d "$old" ]; then
  echo "rolling back to $(basename "$old")" >&2
  point "$BASE/current" "$old"
  activate "$old" || echo "the previous release did not come up either" >&2
elif [ -f "$BASE/app/deploy/proxybot.service" ]; then
  # the first release after the layout without releases/: /opt/proxybot/app and /opt/proxybot/venv are untouched
  echo "rolling back to the old layout in $BASE/app" >&2
  rm -f "$BASE/current"
  activate "$BASE/app" || echo "the old installation did not come up either" >&2
fi
fail "release $(basename "$REL") did not start"
