#!/bin/sh
# Explicit privileged installation stage; never invoked by the daemon or tests.
set -eu
if [ "${1:-}" != "--apply-approved" ] || [ "$(id -u)" -ne 0 ]; then
    echo 'Requires explicit owner approval; run as root with --apply-approved.' >&2
    exit 1
fi
getent group hermod >/dev/null || groupadd --system hermod
getent group hermod-clients >/dev/null || groupadd --system hermod-clients
getent passwd hermod >/dev/null || useradd --system --gid hermod --groups hermod-clients --home-dir /var/lib/hermod --shell /usr/sbin/nologin hermod
install -d -o hermod -g hermod -m 0700 /var/lib/hermod
install -d -o root -g hermod -m 0750 /etc/hermod
echo 'Account/state prepared. No client added, no service installed/enabled/started.'
echo 'Separately approve: usermod -aG hermod-clients haaland'
