#!/usr/bin/env bash
# Validates Kometa's configuration (kometa/, or the directory given) with the Kometa image pinned in compose.yaml
# and the JSON schemas from the same release, without any secrets. The placeholders are replaced by dummy values
# first: Kometa's schema validation sees neither its environment nor a placeholder's value, and a placeholder URL
# fails the schema.
#
# Passes only if Kometa exits 0, prints "Result: PASSED" (without network it gives up, exits 0 and prints no
# result) and lists no unknown keys in its Schema Gap Report (those don't fail Kometa's own check). Validating
# config.yml checks every file it links; Kometa's --validate-dir and --validate-file don't check files (v2.5.2).
# Schema validation can't tell a valid plex_search attribute from an invalid one; only a real run can.
#
# Usage: scripts/kometa-validate.sh [DIR]          validate DIR (default: kometa/), which holds config.yml
#        scripts/kometa-validate.sh --print-image  print the pinned image (name:tag@digest)
#        scripts/kometa-validate.sh --print-tag    print its release tag
# Environment:
#   KOMETA_IMAGE         validate with this image (name:vX.Y.Z@digest) instead of the one pinned in compose.yaml
#                        (the weekly upstream watch tries the latest release this way)
#   KOMETA_SCHEMA_PATH   Kometa's json-schema/ directory at the image's release tag; when unset, it is fetched
#                        with git into a temporary directory (needs network)
#   KOMETA_LOG           a file to keep Kometa's full output in
#   GITHUB_STEP_SUMMARY  the report is appended there too, when set (CI)
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)

image=${KOMETA_IMAGE:-}
[ -n "$image" ] || image=$(docker compose --project-directory "$root" -f "$root/compose.yaml" --env-file "$root/.env.example" \
  config --format json | python3 -c 'import json, sys; print(json.load(sys.stdin)["services"]["kometa"]["image"])')
tag=${image#*:}
tag=${tag%@*}
if ! [[ "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Kometa's image in compose.yaml has no release tag (vX.Y.Z): $image" >&2
  exit 2
fi
case "${1:-}" in
  --print-image) echo "$image"; exit 0 ;;
  --print-tag) echo "$tag"; exit 0 ;;
esac

dir=${1:-$root/kometa}
if [ ! -f "$dir/config.yml" ]; then
  echo "No config.yml in $dir" >&2
  exit 2
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

schema=${KOMETA_SCHEMA_PATH:-}
if [ -z "$schema" ]; then
  echo "Fetching Kometa's JSON schemas at $tag"
  git -c advice.detachedHead=false clone --quiet --depth 1 --branch "$tag" --filter=blob:none --sparse \
    https://github.com/Kometa-Team/Kometa.git "$work/upstream"
  git -C "$work/upstream" sparse-checkout set json-schema
  schema=$work/upstream/json-schema
fi
# Without its schemas Kometa skips schema validation with a warning and still passes.
if [ ! -f "$schema/config-schema.json" ]; then
  echo "No Kometa JSON schemas in $schema" >&2
  exit 2
fi

# The configuration with a dummy value for each placeholder: a URL for addresses and webhooks, a path for folders,
# a 32-character string for keys and tokens.
mkdir "$work/config"
cp "$dir"/*.yml "$work/config/"
sed -E \
  -e 's#<<[A-Z][A-Z0-9_]*(_URL|WEBHOOK)>>#https://example.com#g' \
  -e 's#<<([A-Z][A-Z0-9_]*(ROOT_FOLDER|PLEX_PATH))>>#/data/\1#g' \
  -e 's#<<[A-Z][A-Z0-9_]*>>#aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa#g' \
  "$dir/config.yml" >"$work/config/config.yml"

echo "Validating $dir with $image"
log=$work/kometa.log
code=0
docker run --rm --user "$(id -u):$(id -g)" -v "$work/config:/config" -v "$schema:/schema:ro" "$image" \
  --validate --validate-level structure --validate-schema --schema-path /schema >"$log" 2>&1 || code=$?
if [ -n "${KOMETA_LOG:-}" ]; then cp "$log" "$KOMETA_LOG"; fi

# Kometa's report, without its box drawing.
report=$(sed -n '/Validation Report/,/Result:/p' "$log" | sed -E 's/^\| ?//; s/ *\|$//' | grep -v -E '^ *=* *$' || true)

failures=()
if [ "$code" -ne 0 ]; then failures+=("Kometa exited $code"); fi
if grep -q 'Result: FAILED' "$log"; then
  failures+=("Result: FAILED")
elif ! grep -q 'Result: PASSED' "$log"; then
  failures+=("no result (Kometa needs network to validate)")
fi
# Each unknown key is listed as "- <path>  (seen in N file(s))" under the Schema Gap Report.
if grep -q -E '\(seen in [0-9]+ files?\)' "$log"; then
  failures+=("keys the schema doesn't know (Schema Gap Report)")
fi

if [ ${#failures[@]} -eq 0 ]; then status=passed; else status=failed; fi
{
  echo "Kometa config ($dir, $image): $status"
  for failure in ${failures[@]+"${failures[@]}"}; do echo "- $failure"; done
  echo "$report"
} | tee "$work/summary.txt"

if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  {
    echo "### $(head -1 "$work/summary.txt")"
    tail -n +2 "$work/summary.txt" | grep '^- ' || true
    echo
    echo '```text'
    echo "$report"
    echo '```'
  } >>"$GITHUB_STEP_SUMMARY"
fi

[ "$status" = passed ]
