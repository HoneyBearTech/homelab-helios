#!/usr/bin/env bash
# The check the pull agent runs on the server after each deploy of main (homelab-pull 0.5.0 and later, whose CHECK
# setting names this file): Kometa's configuration with the server's real values, which CI can't check (it
# validates kometa/ with a dummy value for each placeholder). It runs `--validate --validate-level full` in a
# one-off container of the kometa service (`docker compose run --rm --no-deps`: the same image, settings and
# mounts, so Kometa reads the real values from the .env in its data directory), which validates and exits. It
# never starts a Kometa run, and the kometa container that's running is left alone.
#
# It validates only when Kometa may have changed since the commit the check last passed on: kometa/ differs, or the
# kometa service's own lines in compose.yaml do (its image among them), or there's no such commit. Otherwise it
# passes at once.
#
# Passes (exit 0) only if Kometa exits 0 and prints "Result: PASSED" (without network Kometa gives up, exits 0 and
# prints no result). Exits 1 otherwise: the agent then records the deploy's check as failed (`failed:check`, which
# alerts), keeps the deploy, and runs this again when it retries. Kometa's report goes to the output (the agent's
# journal); Kometa's whole output is in logs/meta.log in its data directory too. Kometa's own webhooks (errors, a
# newer version) can fire, as on any Kometa start.
#
# Environment, set by the agent:
#   HOMELAB_PULL_DEPLOYED  the commit deployed (required)
#   HOMELAB_PULL_CHECKED   the commit the check last passed on; empty when it never did
# and optionally:
#   KOMETA_CHECK_TIMEOUT   seconds the validation may take before it's stopped and fails (default 480; keep it below
#                          the agent's CHECK_TIMEOUT, 600 by default)
set -euo pipefail

cd "$(dirname "$0")/.."

deployed=${HOMELAB_PULL_DEPLOYED:?the commit deployed, which the pull agent sets}
checked=${HOMELAB_PULL_CHECKED:-}
limit=${KOMETA_CHECK_TIMEOUT:-480}
name=kometa-post-deploy-check
case $limit in
'' | *[!0-9]*)
  echo "KOMETA_CHECK_TIMEOUT must be a number of seconds" >&2
  exit 2
  ;;
esac

# The kometa service's lines in compose.yaml at a commit: from "  kometa:" up to the next top-level key, service or
# comment between services.
kometa_service() {
  git show "$1:compose.yaml" 2>/dev/null |
    awk '/^  kometa:/ { s = 1; print; next } s && (/^[^ ]/ || /^  [^ ]/) { s = 0 } s'
}

if [ -n "$checked" ] && git cat-file -e "$checked^{commit}" 2>/dev/null; then
  since=$(git rev-parse --short "$checked")
  if git diff --quiet "$checked" "$deployed" -- kometa/ &&
    [ "$(kometa_service "$checked")" = "$(kometa_service "$deployed")" ]; then
    echo "Kometa hasn't changed since $since, where this check last passed: nothing to check"
    exit 0
  fi
  echo "Kometa changed since $since: validating its configuration with the real values"
else
  echo "No earlier passing check to compare with: validating Kometa's configuration with the real values"
fi

log=$(mktemp)
trap 'rm -f "$log"' EXIT
# A container left by a check that was killed would block the name.
docker rm -f "$name" >/dev/null 2>&1 || true

code=0
timeout --kill-after=20 "$limit" docker compose run --rm --no-deps -T --name "$name" kometa \
  --validate --validate-level full </dev/null >"$log" 2>&1 || code=$?

failure=""
case $code in
0)
  if grep -q 'Result: FAILED' "$log"; then
    failure="Result: FAILED"
  elif ! grep -q 'Result: PASSED' "$log"; then
    failure="Kometa printed no result (it needs network to validate)"
  fi
  ;;
124 | 137)
  # `docker compose run` was stopped; the container it started may still be running.
  docker rm -f "$name" >/dev/null 2>&1 || true
  failure="the validation didn't finish within ${limit}s (KOMETA_CHECK_TIMEOUT)"
  ;;
*) failure="docker compose run (Kometa) exited $code" ;;
esac

# Kometa's report, without its box drawing; its last lines when it printed none.
report=$(sed -n '/Validation Report/,/Result:/p' "$log" | sed -E 's/^\| ?//; s/ *\|$//' | grep -v -E '^ *=* *$' || true)
if [ -n "$report" ]; then
  printf '%s\n' "$report"
else
  echo "Kometa's last lines:"
  tail -n 30 "$log"
fi

if [ -z "$failure" ]; then
  echo "Kometa check: passed"
  exit 0
fi
echo "Kometa check: failed: $failure (Kometa's whole output: logs/meta.log in its data directory)" >&2
exit 1
