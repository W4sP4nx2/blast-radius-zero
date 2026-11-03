#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(id -u)" != 0 ]]; then
  echo 'Run with sudo on the dedicated Linux Docker host.' >&2
  exit 1
fi
command -v iptables >/dev/null
command -v ip6tables >/dev/null
command -v docker >/dev/null
docker info >/dev/null
iptables -w -C FORWARD -j DOCKER-USER || {
  echo 'Docker iptables backend required; do not disable Docker firewall management.' >&2
  exit 1
}
if ! docker network inspect brz-egress >/dev/null 2>&1; then
  docker network create --driver bridge --subnet 172.29.250.0/24 \
    --opt com.docker.network.bridge.name=brz-egress \
    --label brz.role=egress brz-egress >/dev/null
fi
python3 deploy/firewall_policy.py install "$@"
echo 'Policy installed. Re-run after reboot/firewall changes, before starting the worker.'
