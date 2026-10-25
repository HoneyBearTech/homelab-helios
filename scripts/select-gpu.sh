#!/usr/bin/env bash
# Points Plex at the GPU this host has right now, for a host whose GPU can change between boots: a virtual machine
# that a failover restarts on another hypervisor with another card passed through (an NVIDIA card on one, an Intel
# one on the other). Run at every boot by deploy/systemd/homelab-helios-gpu.service, or by hand.
#
# It makes compose.host-gpu.yaml, a gitignored symlink in the checkout, point at the override for the GPU it finds:
#   an NVIDIA GPU on the nvidia driver           -> compose.gpu.yaml   (a device reservation, NVENC/NVDEC)
#   an Intel GPU on i915 or xe, with a render node -> compose.intel.yaml (/dev/dri, Quick Sync / VA-API)
#   neither                                      -> compose.cpu.yaml   (Plex transcodes on the CPU)
# NVIDIA wins when both are present. The stack follows the link only when COMPOSE_FILE names it, in .env and in the
# pull agent's settings: COMPOSE_FILE=compose.yaml:compose.host-gpu.yaml. When the link changes, it recreates Plex with
# the new override (`docker compose up --detach --no-deps --wait plex`), waiting for Docker to start and taking the
# pull agent's lock first (deploy_lock in lib.sh), so a deploy can't run at the same time. When the link is already
# right it changes nothing: Docker has started Plex as it was.
#
# Exit codes: 0 = the link is right (and Plex was recreated if it changed), 1 = Docker didn't start, the lock or
# `docker compose up` failed.
#
# Environment (for tests and odd hosts):
#   GPU_SYSFS         where sysfs is mounted (default /sys)
#   GPU_DOCKER_WAIT   seconds to wait for Docker to answer (default 300)
#   COMPOSE_FILE      as Docker Compose reads it; when unset, the value in .env
set -euo pipefail

cd "$(dirname "$0")/.."
# shellcheck source=scripts/lib.sh
. scripts/lib.sh

sysfs=${GPU_SYSFS:-/sys}
wait=${GPU_DOCKER_WAIT:-300}
link=compose.host-gpu.yaml

case $wait in
'' | *[!0-9]*)
  echo "GPU_DOCKER_WAIT must be a number of seconds" >&2
  exit 2
  ;;
esac

# Display controllers (PCI class 0x03xxxx) by vendor and the driver bound to them.
nvidia="" intel="" unbound=""
for dev in "$sysfs"/bus/pci/devices/*; do
  [ -r "$dev/class" ] && [ -r "$dev/vendor" ] || continue
  case $(cat "$dev/class") in 0x03*) ;; *) continue ;; esac
  driver=""
  if [ -L "$dev/driver" ]; then driver=$(basename "$(readlink "$dev/driver")"); fi
  name=${dev##*/}
  case $(cat "$dev/vendor"):$driver in
  0x10de:nvidia) nvidia="$nvidia $name" ;;
  0x8086:i915 | 0x8086:xe)
    # A render node is what Plex opens; a display-only device has none.
    if ls "$dev"/drm/renderD* >/dev/null 2>&1; then intel="$intel $name"; fi
    ;;
  0x10de:* | 0x8086:*) unbound="$unbound $name (${driver:-no driver})" ;;
  esac
done

if [ -n "$nvidia" ]; then
  target=compose.gpu.yaml found="NVIDIA GPU on the nvidia driver:$nvidia"
elif [ -n "$intel" ]; then
  target=compose.intel.yaml found="Intel GPU with a render node:$intel"
else
  target=compose.cpu.yaml found="no GPU Plex can use"
fi
echo "Found $found -> $target"
if [ -n "$unbound" ]; then
  echo "Not usable (wrong or no driver):$unbound"
fi

files=${COMPOSE_FILE-}
if [ -z "$files" ] && [ -f .env ]; then
  files=$(sed -n 's/^COMPOSE_FILE=//p' .env | tail -n 1)
  files=${files%\"}
  files=${files#\"}
fi
case :$files: in
*:$link:*) follows=yes ;;
*)
  follows=""
  echo "COMPOSE_FILE (${files:-unset}) doesn't name $link, so the stack doesn't follow it: Plex is left alone"
  ;;
esac

current=$(readlink "$link" 2>/dev/null || true)
if [ "$current" = "$target" ]; then
  echo "$link already points at $target: nothing to change"
  exit 0
fi
# A new link renamed over the old one, so Compose never sees it missing.
ln -sfn "$target" "$link.new"
mv -f "$link.new" "$link"
echo "$link now points at $target (was ${current:-missing})"
[ -n "$follows" ] || exit 0

waited=0
until docker info >/dev/null 2>&1; do
  if [ "$waited" -ge "$wait" ]; then
    echo "error: Docker didn't answer within ${wait}s; Plex wasn't recreated (run this again once it does)" >&2
    exit 1
  fi
  sleep 5
  waited=$((waited + 5))
done
deploy_lock
echo "Recreating Plex with $target"
docker compose up --detach --no-deps --wait --wait-timeout 600 plex
