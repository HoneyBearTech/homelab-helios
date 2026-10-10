#!/usr/bin/env bash
# Back up the stack's state: every service's data mounts (each read-write volume or directory it mounts, such as
# Plex's or Tautulli's database; never the Docker socket, and never a path the service's
# org.honeybeartech.helios.backup.skip label excludes, such as the media library) and the settings files. Paths a
# service's org.honeybeartech.helios.backup.exclude label lists inside a mount (Plex's artwork, Kometa's assets) are
# left out of that mount's archive. Each service is stopped only while its own data is copied, so its database is
# consistent, and started again before the copy is compressed; services with nothing to archive keep running.
#
#   scripts/backup.sh [DIR]      DIR defaults to backups/<date>-<time> in the checkout (gitignored)
#
# DIR gets one <service>--<path>.tar.gz per mount, the settings (.env and any <service>.env) under env/, a MANIFEST
# naming each archive's service, container path, source and image, and SHA256SUMS, all readable only by the user
# who ran it: the archives hold logins, tokens and private keys. Copy it off the host (scripts/scheduled-backup.sh
# does). Restore with scripts/restore.sh. It runs `docker compose` from the checkout, so the standard Compose
# variables (COMPOSE_PROJECT_NAME, COMPOSE_FILE, COMPOSE_ENV_FILES) select another project, as the smoke test does.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=scripts/lib.sh
. "$root/scripts/lib.sh"
cd "$root"
dest=${1:-backups/$(date +%Y%m%d-%H%M%S)}
# pigz compresses on every core; gzip on one is several times slower on large archives.
compress=$(command -v pigz || command -v gzip)

if [ -e "$dest" ] && [ -n "$(ls -A "$dest")" ]; then
  echo "error: $dest already exists and isn't empty" >&2
  exit 1
fi
umask 077
mkdir -p "$dest/env"
dest=$(cd "$dest" && pwd)

# Every service needs a container (running or stopped) to read its mounts from. A tool that has never been started
# (a service in tool_profiles, such as Quickstart) has no data yet and is skipped.
services=()
always_on=" $(COMPOSE_PROFILES='' docker compose config --services | tr '\n' ' ') "
for service in $(docker compose config --services); do
  if [ -z "$(docker compose ps --all --quiet "$service")" ]; then
    if [[ "$always_on" != *" $service "* ]]; then
      echo "Skipping $service (a tool that has never been started: no data yet)"
      continue
    fi
    echo "error: $service has no container; run 'docker compose create' or 'docker compose up -d' first" >&2
    exit 1
  fi
  services+=("$service")
done

# Starts again whatever was running and is stopped now: the service stopped for its backup, and any service Compose
# stopped along with it (one that depends on it).
running=$(docker compose ps --services --status running)
start_again() {
  if [ -n "$running" ]; then
    # shellcheck disable=SC2086 # one service name per word
    docker compose start $running
  fi
}
finish() {
  status=$?
  start_again || status=1
  exit "$status"
}
trap finish EXIT

printf '# archive\tservice\tmount\tsource\timage\n' >"$dest/MANIFEST"
for service in "${services[@]}"; do
  id=$(docker compose ps --all --quiet "$service")
  image=$(docker inspect --format '{{.Config.Image}}' "$id")
  while IFS= read -r mount; do
    echo "Skipping $service $mount (excluded from backups by its $skip_label label)"
  done < <(skipped_mounts "$id")
  mounts=()
  while IFS=$'\t' read -r mount source; do
    if is_dir "$id" "$mount"; then
      mounts+=("$mount"$'\t'"$source")
    else
      echo "Skipping $service $mount (not a directory)"
    fi
  done < <(data_mounts "$id")
  if [ ${#mounts[@]} -eq 0 ]; then continue; fi

  if [[ $'\n'"$running"$'\n' == *$'\n'"$service"$'\n'* ]]; then
    echo "Stopping $service"
    docker compose stop "$service"
  fi
  archives=()
  for entry in "${mounts[@]}"; do
    IFS=$'\t' read -r mount source <<<"$entry"
    archive=$(archive_name "$service" "$mount")
    echo "Archiving $service $mount ($source)"
    # A mount inside this one (Plex's cache inside its /config) is archived or skipped on its own, and the paths the
    # service's exclude label lists are left out.
    excludes=()
    while IFS= read -r path; do
      echo "  leaving out $path"
      excludes+=("--exclude=./${path#"$mount"/}")
    done < <(left_out "$id" "$mount")
    # tar runs as root in the container so it can read every file; the archive itself is written by this shell,
    # so it belongs to the user running the backup. Uncompressed here: compressing takes far longer than copying,
    # and the service stays stopped only for the copy. No log driver: Docker's default one would also write the whole
    # archive, which arrives on stdout, into the container's log, and the copy would take several times as long.
    docker run --rm --log-driver none --network none --volumes-from "$id:ro" "$busybox" \
      tar -cf - "${excludes[@]+"${excludes[@]}"}" -C "$mount" . </dev/null >"$dest/${archive%.gz}"
    printf '%s\t%s\t%s\t%s\t%s\n' "$archive" "$service" "$mount" "$source" "$image" >>"$dest/MANIFEST"
    archives+=("$archive")
  done
  start_again
  for archive in "${archives[@]}"; do
    "$compress" -c "$dest/${archive%.gz}" >"$dest/$archive"
    rm "$dest/${archive%.gz}"
  done
done

# The settings: .env and any service's env file, or only the files in COMPOSE_ENV_FILES when that's set (the smoke
# test, which must never copy the real ones).
if [ -n "${COMPOSE_ENV_FILES:-}" ]; then
  IFS=, read -r -a env_files <<<"$COMPOSE_ENV_FILES"
else
  env_files=(.env *.env)
fi
for file in "${env_files[@]}"; do
  if [ -f "$file" ]; then cp "$file" "$dest/env/$(basename "$file")"; fi
done

files=$(cd "$dest" && find . -type f | sed 's|^\./||' | sort)
(cd "$dest" && while read -r f; do sha256 "$f"; done <<<"$files" >SHA256SUMS)
echo "Backup written to $dest ($(du -sh "$dest" | cut -f1)). It holds secrets: copy it off the host, privately."
