#!/usr/bin/env bash
# Points Plex, and an Argus agent beside the stack, at the GPU this host has right now, for a host whose GPU can
# change between boots: a virtual machine that a failover restarts on another hypervisor with another card passed
# through (an NVIDIA card on one, an Intel one on the other). Run at every boot by
# deploy/systemd/homelab-helios-gpu.service, or by hand.
#
# It makes compose.host-gpu.yaml, a gitignored symlink in the checkout, point at the override for the GPU it finds:
#   an NVIDIA GPU on the nvidia driver           -> compose.gpu.yaml   (a device reservation, NVENC/NVDEC)
#   an Intel GPU on i915 or xe, with a render node -> compose.intel.yaml (/dev/dri, Quick Sync / VA-API)
#   neither                                      -> compose.cpu.yaml   (Plex transcodes on the CPU)
# NVIDIA wins when both are present. The stack follows the link only when COMPOSE_FILE names it, in .env and in the
# pull agent's settings: COMPOSE_FILE=compose.yaml:compose.host-gpu.yaml. When the link changes, it recreates Plex with
# the new override (`docker compose up --detach --no-deps --wait plex`), waiting for Docker to start and taking the
# pull agent's lock first (deploy_lock in lib.sh), so a deploy can't run at the same time.
#
# The Argus agent (https://github.com/HoneyBearTech/Argus, agent/compose.yml) in GPU_ARGUS_AGENT_DIR follows the GPU
# too: its `gpu` Compose profile runs an NVIDIA GPU exporter, which can't start without an NVIDIA GPU, and its
# `intel-gpu` profile an Intel GPU exporter (intel_gpu_top). The COMPOSE_PROFILES line of the agent's .env keeps the
# profile of the GPU chosen for Plex above and drops the other: `gpu` for compose.gpu.yaml, `intel-gpu` for
# compose.intel.yaml, neither for compose.cpu.yaml. A profile the agent's compose file doesn't define yet starts
# nothing (Compose ignores it), so the line can name `intel-gpu` before the agent has it. When that changes, it
# removes the agent's services that only the old profiles start (`docker compose rm --stop --force`: `up
# --remove-orphans` leaves a service whose profile was dropped running) and starts those only the new ones do (`docker
# compose up --detach --wait`), then rewrites the line. The agent's other containers stay as they
# are. The line is rewritten only once the containers have changed, so after a failure the next run tries again. The
# pull agent doesn't deploy the Argus agent, so this part needs no lock.
#
# When the link and the agent's profiles are already right it changes nothing: Docker has started both as they were.
#
# Every run, changed or not, records the GPU it chose as one series for the Argus agent's textfile collector:
# homelab_gpu_selected{vendor="nvidia"}, {vendor="intel"} or {vendor="none"}, always 1, in homelab-helios-gpu.prom in
# GPU_METRICS_DIR (the pull agent's metrics directory, which the agent's node exporter reads). Argus uses it to expect
# the NVIDIA GPU exporter only while there is an NVIDIA GPU. A new file is renamed over the old one, so the collector
# never reads half of one. Nothing is written when that directory doesn't exist (no pull agent here).
#
# Exit codes: 0 = the link and the agent's profiles are right (and what changed was applied), 1 = Docker didn't start,
# or the metric couldn't be written, or the lock, Plex's `docker compose up` or the agent's change failed (a failure
# with one of these doesn't stop the others).
#
# Environment (for tests and odd hosts):
#   GPU_SYSFS            where sysfs is mounted (default /sys)
#   GPU_DOCKER_WAIT      seconds to wait for Docker to answer (default 300)
#   GPU_ARGUS_AGENT_DIR  the Argus agent's folder (default ~/argus-agent; empty: leave the agent alone); nothing is
#                        done there when it has no .env
#   GPU_METRICS_DIR      where the metric goes (default: the pull agent's metrics directory,
#                        ${HOMELAB_PULL_STATE_DIR:-${XDG_STATE_HOME:-~/.local/state}/homelab-pull}/metrics, as in
#                        lib.sh's deploy_lock; empty: no metric)
#   COMPOSE_FILE         as Docker Compose reads it; when unset, the value in .env
set -euo pipefail

cd "$(dirname "$0")/.."
# shellcheck source=scripts/lib.sh
. scripts/lib.sh

sysfs=${GPU_SYSFS:-/sys}
wait=${GPU_DOCKER_WAIT:-300}
agent=${GPU_ARGUS_AGENT_DIR-$HOME/argus-agent}
metrics=${GPU_METRICS_DIR-${HOMELAB_PULL_STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/homelab-pull}/metrics}
link=compose.host-gpu.yaml

case $wait in
'' | *[!0-9]*)
  echo "GPU_DOCKER_WAIT must be a number of seconds" >&2
  exit 2
  ;;
esac

# The value env file $1 gives setting $2 (the last line wins, as in Compose), without double quotes.
env_value() {
  local value
  value=$(sed -n "s/^$2=//p" "$1" | tail -n 1)
  value=${value%\"}
  printf '%s\n' "${value#\"}"
}

# Moves the Argus agent from profiles $profiles to $wanted: removes the services only the old ones start, starts
# those only the new ones do, then rewrites COMPOSE_PROFILES in its .env. In a subshell, in the agent's folder: the
# agent is a Compose project of its own, so this stack's COMPOSE_FILE mustn't reach it, and each command names the
# profiles it needs (an empty COMPOSE_PROFILES means none, and overrides lib.sh's and the .env's).
retarget_agent() (
  cd "$agent" || exit 1
  unset COMPOSE_FILE COMPOSE_PROJECT_NAME
  old=" $(COMPOSE_PROFILES=$profiles docker compose config --services | tr '\n' ' ')" || exit 1
  new=" $(COMPOSE_PROFILES=$wanted docker compose config --services | tr '\n' ' ')" || exit 1
  gone="" added=""
  for service in $old; do
    case $new in *" $service "*) ;; *) gone="$gone $service" ;; esac
  done
  for service in $new; do
    case $old in *" $service "*) ;; *) added="$added $service" ;; esac
  done
  echo "Moving the Argus agent from COMPOSE_PROFILES=$profiles to COMPOSE_PROFILES=$wanted"
  # shellcheck disable=SC2086 # one word per service
  if [ -n "$gone" ]; then
    echo "Removing the Argus agent's$gone"
    COMPOSE_PROFILES=$profiles docker compose rm --stop --force $gone || exit 1
  fi
  # shellcheck disable=SC2086 # one word per service
  if [ -n "$added" ]; then
    echo "Starting the Argus agent's$added"
    COMPOSE_PROFILES=$wanted docker compose up --detach --wait --wait-timeout 300 $added || exit 1
  fi
  # A new file renamed over the old one, with its mode (the .env holds the agent's password).
  cp -p .env .env.new || exit 1
  awk -v line="COMPOSE_PROFILES=$wanted" '
    /^COMPOSE_PROFILES=/ { print line; found = 1; next }
    { print }
    END { if (!found) print line }
  ' .env >.env.new || exit 1
  mv -f .env.new .env || exit 1
  echo "The Argus agent's .env now has COMPOSE_PROFILES=$wanted"
)

# Writes homelab_gpu_selected{vendor="$1"} 1 to $metrics/homelab-helios-gpu.prom: a new file renamed over the old one,
# named so the collector (which reads *.prom) skips it until then.
write_metric() {
  local out=$metrics/homelab-helios-gpu.prom
  if ! {
    echo "# HELP homelab_gpu_selected The GPU select-gpu.sh last chose for Plex (vendor: nvidia, intel or none)."
    echo "# TYPE homelab_gpu_selected gauge"
    echo "homelab_gpu_selected{vendor=\"$1\"} 1"
  } >"$out.tmp.$$" || ! mv -f "$out.tmp.$$" "$out"; then
    rm -f "$out.tmp.$$"
    echo "error: couldn't write the metric to $out" >&2
    return 1
  fi
  echo "Wrote homelab_gpu_selected{vendor=\"$1\"} to $out"
}

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
  target=compose.gpu.yaml vendor=nvidia found="NVIDIA GPU on the nvidia driver:$nvidia"
elif [ -n "$intel" ]; then
  target=compose.intel.yaml vendor=intel found="Intel GPU with a render node:$intel"
else
  target=compose.cpu.yaml vendor=none found="no GPU Plex can use"
fi
echo "Found $found -> $target"
if [ -n "$unbound" ]; then
  echo "Not usable (wrong or no driver):$unbound"
fi

status=0
if [ -z "$metrics" ]; then
  :
elif [ -d "$metrics" ]; then
  write_metric "$vendor" || status=1
else
  echo "No metrics directory $metrics (no pull agent here): no metric written"
fi

files=${COMPOSE_FILE-}
if [ -z "$files" ] && [ -f .env ]; then files=$(env_value .env COMPOSE_FILE); fi
case :$files: in
*:$link:*) follows=yes ;;
*)
  follows=""
  echo "COMPOSE_FILE (${files:-unset}) doesn't name $link, so the stack doesn't follow it: Plex is left alone"
  ;;
esac

recreate=""
current=$(readlink "$link" 2>/dev/null || true)
if [ "$current" = "$target" ]; then
  echo "$link already points at $target"
else
  # A new link renamed over the old one, so Compose never sees it missing.
  ln -sfn "$target" "$link.new"
  mv -f "$link.new" "$link"
  echo "$link now points at $target (was ${current:-missing})"
  recreate=$follows
fi

# The Argus agent's profiles now ($profiles) and the ones it should have ($wanted): the same without the GPU
# profiles, and the GPU's own ($gpu_profile) last.
case $vendor in
nvidia) gpu_profile=gpu ;;
intel) gpu_profile="intel-gpu" ;;
*) gpu_profile="" ;;
esac
retarget="" profiles="" wanted=""
if [ -n "$agent" ] && [ -f "$agent/.env" ]; then
  profiles=$(env_value "$agent/.env" COMPOSE_PROFILES)
  has=""
  saved_ifs=$IFS
  IFS=,
  for profile in $profiles; do
    case $profile in
    gpu | intel-gpu) has="$has $profile" ;;
    '') ;;
    *) wanted=${wanted:+$wanted,}$profile ;;
    esac
  done
  IFS=$saved_ifs
  if [ -n "$gpu_profile" ]; then wanted=${wanted:+$wanted,}$gpu_profile; fi
  if [ "$has" = "${gpu_profile:+ $gpu_profile}" ]; then
    echo "The Argus agent's COMPOSE_PROFILES=$profiles already fits the GPU"
  else
    retarget=yes
  fi
elif [ -n "$agent" ]; then
  echo "No Argus agent in $agent (no .env): left alone"
fi

[ -n "$recreate" ] || [ -n "$retarget" ] || exit "$status"

waited=0
until docker info >/dev/null 2>&1; do
  if [ "$waited" -ge "$wait" ]; then
    echo "error: Docker didn't answer within ${wait}s" >&2
    if [ -n "$recreate" ]; then
      echo "Plex wasn't recreated: once Docker answers, run \`docker compose up --detach --wait plex\` here" >&2
    fi
    if [ -n "$retarget" ]; then
      echo "The Argus agent wasn't changed: run this again once Docker answers" >&2
    fi
    exit 1
  fi
  sleep 5
  waited=$((waited + 5))
done

if [ -n "$recreate" ]; then
  if deploy_lock; then
    echo "Recreating Plex with $target"
    docker compose up --detach --no-deps --wait --wait-timeout 600 plex || status=1
  else
    status=1
  fi
fi
if [ -n "$retarget" ]; then
  retarget_agent || status=1
fi
exit "$status"
