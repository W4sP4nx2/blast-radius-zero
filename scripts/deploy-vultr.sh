#!/usr/bin/env bash
# Provision an Ubuntu 24.04 x86_64 host. This script does not call the Vultr API.
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run as root on the intended Vultr VM." >&2
  exit 1
fi
if [[ $(uname -s) != Linux || $(uname -m) != x86_64 ]]; then
  echo "This pinned provisioning path supports Linux x86_64 only." >&2
  exit 1
fi

NATIVE_REPOSITORY=https://github.com/withnative/native.git
NATIVE_COMMIT=94352f9d90e62720e23c66269e2fe663f205e1c7
NATIVE_SOURCE=/opt/brz/native-source
NATIVE_HOME=/var/lib/brz/native
NATIVE_MCP_BINARY=/usr/local/lib/brz/mcp-stdio
RUSTUP_VERSION=1.28.2
RUSTUP_SHA256=20a06e644b0d9bd2fbdbfd52d42540bdde820ea7df86e92e533c073da0cdd43c
RUST_TOOLCHAIN=1.98.0

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates curl git build-essential pkg-config libssl-dev \
  docker.io docker-compose-v2
systemctl enable --now docker

rustup_init=/tmp/rustup-init
curl --fail --silent --show-error --location \
  --proto '=https' --tlsv1.2 \
  "https://static.rust-lang.org/rustup/archive/${RUSTUP_VERSION}/x86_64-unknown-linux-gnu/rustup-init" \
  --output "${rustup_init}"
printf '%s  %s\n' "${RUSTUP_SHA256}" "${rustup_init}" | sha256sum --check --status
chmod 0700 "${rustup_init}"
"${rustup_init}" -y --profile minimal --default-toolchain "${RUST_TOOLCHAIN}"
rm -f "${rustup_init}"
export PATH=/root/.cargo/bin:${PATH}

install -d -m 0755 /opt/brz "${NATIVE_HOME}" "$(dirname "${NATIVE_MCP_BINARY}")"
if [[ ! -d ${NATIVE_SOURCE}/.git ]]; then
  git clone --filter=blob:none --no-checkout "${NATIVE_REPOSITORY}" "${NATIVE_SOURCE}"
elif [[ $(git -C "${NATIVE_SOURCE}" remote get-url origin) != "${NATIVE_REPOSITORY}" ]]; then
  echo "Refusing to reuse ${NATIVE_SOURCE}: unexpected Git origin." >&2
  exit 1
fi
git -C "${NATIVE_SOURCE}" fetch --depth=1 origin "${NATIVE_COMMIT}"
git -C "${NATIVE_SOURCE}" checkout --detach "${NATIVE_COMMIT}"
(
  cd "${NATIVE_SOURCE}"
  cargo +"${RUST_TOOLCHAIN}" build --locked --release --bin mcp-stdio
)
install -m 0755 "${NATIVE_SOURCE}/target/release/mcp-stdio" "${NATIVE_MCP_BINARY}"

probe_dir=$(mktemp -d /tmp/brz-native-probe.XXXXXX)
probe_db=${probe_dir}/native.db
trap 'rm -rf "${probe_dir}"' EXIT
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"brz-provision","version":"1.0.0"}}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"engine_info","arguments":{}}}' \
  | NATIVE_CE_MCP_SURFACE=legacy "${NATIVE_MCP_BINARY}" "${probe_db}" \
  | python3 -c 'import json,sys; rows=[json.loads(x) for x in sys.stdin if x.strip()]; assert rows[-1]["result"]["structuredContent"]["engine"] == "native-ce"'

install -d -m 0755 /etc/blast-radius-zero
cat >/etc/blast-radius-zero/native.env <<EOF
NATIVE_HOME=${NATIVE_HOME}
NATIVE_MCP_BINARY=${NATIVE_MCP_BINARY}
NATIVE_MCP_DB=${NATIVE_HOME}/native.db
EOF
chmod 0600 /etc/blast-radius-zero/native.env

cat <<EOF
Native MCP ${NATIVE_COMMIT} is installed and passed engine_info.
It is a local stdio context engine, not a code/browser sandbox and exposes no port.
Keep SANDBOX_RUNTIME=docker until a Native execution API passes NATIVE_SPEC.md gates.
EOF

if [[ ${DEPLOY_APPLICATION:-0} == 1 ]]; then
  repository_root=$(cd "$(dirname "$0")/.." && pwd)
  cd "${repository_root}"
  if [[ ! -f .env ]]; then
    echo "Create a permission-restricted .env before DEPLOY_APPLICATION=1." >&2
    exit 1
  fi
  docker compose --profile images build
  docker compose up -d
  ./deploy/preflight.sh
fi
