# homelab-helios

The Docker Compose stack for Helios, the owner's homelab media server (Ubuntu 24.04, amd64, a VM with an NVIDIA
GPU passed through): Plex, Tautulli, AURA (MediUX artwork), Kometa and ImageMaid, with autoheal (and Kometa Quickstart as an on-demand tool), every image pinned by tag and digest so
the server can be upgraded and rebuilt from this repository. The tooling (checker, backup scripts, smoke test,
CI, release workflow) and `compose.yaml` (+ `compose.gpu.yaml`) are in place; the services still run from their
old setup on the host until the cutover (plan in Chronos).

## Before Making Structural Changes
Read the project's notes first. They live outside this repo, in the owner's Obsidian vault **Chronos** at
`~/Chronos/Projects/homelab-helios/` (every file is prefixed `homelab-helios-`):
- `homelab-helios-roadmap.md`: phases with checkboxes, the owner's open questions, the OpenSSF phase and the
  owner's manual GitHub steps
- `homelab-helios-Pass-Map.md`: pass-by-pass delivery log; add a row when a pass ships
- `homelab-helios-Architecture.md`: the host, which containers run there today and which belong in this repo,
  data flow, deployment shape, cutover plan
- `homelab-helios-Security-Considerations.md`: assets, threats, trust boundaries, checklist (Plex is the
  household's media server and may be reachable from the internet: treat these notes as load-bearing)
- `homelab-helios-Decisions-Log.md`: ADR-style log (entries marked **Proposed** still need the owner's call)

Keep them current as work lands: tick roadmap checkboxes, add a Pass-Map row per pass, add dated
Decisions-Log entries. **The notes never go into this repo.** Chronos is versioned in its own private repo;
only commit or push it when the owner asks. The old in-repo vault path `.obsidian-docs/` stays gitignored.

The sibling repos `~/GitHub/homelab-ares`, `~/GitHub/homelab-atlas` and `~/GitHub/homelab-deimos` follow the same
pattern; ares is the template for tooling, workflows and policy files, and this repo was bootstrapped from
deimos (the closest match: an NVIDIA GPU, a media library on a network share).

## This repo is public
- No hostnames, IP addresses, internal or public domains, host paths, NFS exports, Portainer stack names, Plex
  server names, Plex account names or personal email addresses in anything committed: code, compose, the
  docs, examples, tests, commit messages. Host facts live only in the Chronos notes. Examples use
  placeholders (`/srv/appdata`, `/srv/media`, `example.com`, `homelab-helios_`).
- Commit as `31805425+HoneyBearTech@users.noreply.github.com` (set as this repo's `user.email`), with
  `git commit -s` for the DCO sign-off; commits and tags are SSH-signed.
- No secrets: Plex's server token, the Plex tokens Tautulli, AURA, Kometa and ImageMaid hold, AURA's MediUX
  token, Kometa's API keys (in its `config.yml`) and logins stay in the
  services' data on the host, never in `compose.yaml`, `.env` or the `*.example` files. A secret a service can
  only take from its environment gets its own gitignored `<service>.env` (`env_file`) with a committed
  `<service>.env.example`: Plex's one-time `PLEX_CLAIM` goes in `plex.env`. `.gitignore` covers `.env`, keys,
  certificates, `appdata/`, `data/`, `media/`, `transcode/`, `backups/`; extend it rather than work around it.
- Keep the repo on track for OpenSSF Baseline Levels 1 and 2 and the Best Practices Passing and Silver
  badges (project 15291). If a change would break a met criterion (for example unpinning an image or an
  Action, adding a workflow without `permissions:`, or dropping the coverage floor), say so before making it.

## Rules for the stack
- **Every image is pinned as `name:tag@sha256:<digest>`.** Never `latest`, never tag-only. Dependabot
  (`docker-compose` ecosystem) updates tag and digest together. Patch, minor and major updates auto-merge once
  the required checks pass (Plex included: it can't touch the media; majors too, owner 2026-10-08). A merge
  never deploys: Helios changes only on a deliberate pull, and a major's release notes are read before it
  (it can migrate a service's data one way).
- **Amd64.** Every image must publish `linux/amd64`. The smoke test runs on `ubuntu-latest` and the image scan
  scans `linux/amd64`.
- **The GPU is optional to CI.** GitHub's runners have no GPU, so the NVIDIA device reservation must not stop
  the stack from starting without one (`compose.gpu.yaml`, owner 2026-10-07). GPU access is a device reservation, never `privileged: true`.
- **The media library is mounted read-write into Plex and AURA only** (owner 2026-10-07: AURA saves artwork
  there and Plex's media deletion stays possible), and is never backed up, restored or deleted by this repo's
  scripts. It is far too large and is protected by the NAS. A service lists such paths in its
  `org.honeybeartech.helios.backup.skip` label (comma-separated container paths); `backup.sh` skips them,
  `restore.sh` refuses to write them, and the smoke test checks both. Plex's must list `/media`, its
  cache and `/transcode`; AURA's `/media` and `/kometa`; Kometa's `/auraassets`; ImageMaid's `/plex` and `/plex/Cache` (the
  overlapping mounts are backed up once, with the service that owns the data).
- **No privileged containers, added capabilities, host network/PID or Docker socket mounts** unless the
  service carries `org.honeybeartech.helios.allow.<rule>: "<reason>"` and the owner agreed (Plex runs on the
  stack's network, publishing only 32400: owner 2026-10-07; it ran in host mode before the cutover). `scripts/check_compose.py` enforces it in CI
  and in the release workflow.
- **Every service has a health check** and the `autoheal: "true"` label. autoheal (`willfarrell/autoheal`)
  behind `lscr.io/linuxserver/socket-proxy` (read-only socket, internal `docker-proxy` network) is part of the
  first `compose.yaml`, exactly as on homelab-atlas/ares (owner 2026-10-07); its webhook URL goes in the
  gitignored `autoheal.env`. The smoke test checks autoheal restarts a service that turns unhealthy.
- **Never change the live server** (Helios) without the owner asking: no `docker compose up`, no edits to
  service data, Plex libraries or settings, or Portainer stacks. Read-only inspection (`docker ps`,
  `docker inspect`) only when asked (host quirks for doing so are in the Chronos Architecture note).
- Every setting goes through `.env` (`${VAR:?…}` in compose when required) and is listed in `.env.example`
  and `docs/interfaces.md`.
- **Container paths, image family and ports are load-bearing**: Plex stores library paths (`/media/...`) in its
  database, and the LinuxServer.io image family (Plex, Tautulli) lays out `/config` its own way; players, Tautulli, plex-director-mcp and the
  reverse proxy reach the services by their published ports. Adopt the existing data and keep paths, image
  family and ports the same; see the cutover plan in Chronos.

## Kometa
Kometa's configuration is moving into the repo (`kometa/`, **Planned**; the Decisions-Log entries from
2026-10-08), with CI validation and a weekly upstream watch.
- **Secrets and host facts in Kometa's YAML are placeholders**: `<<UPPER_SNAKE>>`, which Kometa fills from
  the `KOMETA_<UPPER_SNAKE>` environment variable (`<<lower_snake>>` doesn't match, and an unmatched
  placeholder silently becomes empty). That covers tokens, API keys, Plex's URL, notification URLs and
  Radarr/Sonarr addresses and root folders. The values go in the gitignored `kometa.env`, never in the repo.
- **Never read Kometa's `config.yml`, its `.bak` copies or `config.cache` on the host as they are**: only
  through the fail-closed redaction script, run on the host, so the secrets never reach your context. Before
  reading any other file of Kometa's from the host, grep it there for secret-looking keys and show the matches
  with values redacted.
- **Verify Kometa's CLI and behaviour against the pinned image** (`docker run --rm <pinned image> --help`),
  never from memory. Known for v2.5.2: validation needs network and a `config.yml`; the image has no
  `json-schema/` (fetch it at the pinned tag and pass `--schema-path`, or schema checks are silently skipped and
  the run still passes). A failed validation exits 1, but without network Kometa gives up after its retries
  and exits 0 with no result, so a gate requires the `Result: PASSED` line as well as exit 0. Pass Kometa's
  flags as separate arguments: given flags it doesn't recognise, it starts its scheduler and waits silently.
  Schema validation passes some configs that fail at run time (a filter attribute such as
  `audio_track_title.regex` used under `plex_search`), so a passing check is not proof the config runs.
- **Kometa's validation is a required check.** Dependabot's patch and minor Kometa updates auto-merge, so the
  validation runs as an always-running job (never path-filtered: a skipped required check blocks the PR).
- Reviews of Kometa's configuration (optimization findings) are private planning: they go in Chronos, not
  `docs/`.

## Stack
- Docker Compose v2 (`compose.yaml`; the GPU in `compose.gpu.yaml`, added on the host via `COMPOSE_FILE`), upstream images: `lscr.io/linuxserver/plex` (with
  `VERSION=docker`, so it never self-updates), `lscr.io/linuxserver/tautulli`, `ghcr.io/mediux-team/aura`,
  `kometateam/kometa` and `kometateam/imagemaid` (release tags, not `nightly`/`develop`), autoheal +
  socket-proxy; `kometateam/quickstart` (release tags) as a **tool** in the `tools` profile: not started by
  `docker compose up -d`, `restart: "no"`, port 7171 on the LAN, no login (owner 2026-10-08:
  config editor only, never its own Kometa/ImageMaid runs or self-updater). Tooling must see the tools: the
  workflows and `make check`/`config` pass `--profile tools`, the scripts get `COMPOSE_PROFILES` from `lib.sh`.
  Not in this repo: Homebox, InvenTree (and its Caddy), TitleCardMaker, Watchtower, Diun, the
  Argus agent and Argus' Loki, the Portainer agent.
- Tooling (ported from homelab-deimos): `scripts/check_compose.py` (Python, standard library only:
  policy check + CycloneDX SBOM), `scripts/backup.sh`, `restore.sh`, `smoke-test.sh`, `lib.sh` (bash, must run
  on macOS' bash 3.2); ruff (`select = ["ALL"]`), yamllint, shellcheck, pytest + coverage (90 % branch floor),
  pip-tools for the hash-pinned `requirements-dev.txt`. CI-only: actionlint, gitleaks, CodeQL, Scorecard,
  dependency review, DCO, Trivy image scan, Dependabot auto-merge (patch/minor).
- Releases (`release.yml`, on a `v*.*.*` tag): policy check, source archive, CycloneDX SBOM,
  `SHA256SUMS` signed with cosign keyless, SLSA provenance, GitHub Release from the tag's `CHANGELOG.md`
  section. No images are built or published.

## Conventions
- `CHANGELOG.md` (Keep a Changelog): add to "Unreleased" with every user-visible change.
- Docs in `docs/` change in the same PR as the behaviour; anything not built yet is marked **Planned**.
- Workflows: top-level `permissions: contents: read` (Scorecard: `read-all`), raise per job; actions pinned by
  full SHA with a version comment; untrusted `${{ github.event.* }}` only through `env:`.
- Required checks in the `main` ruleset: `CI / Checks + tests`, `CI / Stack smoke test`, DCO sign-off,
  Dependency review, CodeQL's Analyze (python) / Analyze (actions). Don't rename those jobs.
- Claude opens a PR for every change and turns on auto-merge for it (`gh pr merge --auto --squash`; owner
  2026-10-08), as on the sibling repos. Never bypass a check or the ruleset.

## Commands
```sh
make test     # checker tests + coverage floor (no Docker, no network)
make lint     # ruff check, ruff format --check, yamllint --strict, shellcheck -x
make check    # docker compose config --format json | scripts/check_compose.py  (needs .env and compose.yaml)
make smoke    # scripts/smoke-test.sh: throwaway project, healthy, backup/restore round trip (needs Docker)
make config   # docker compose config (resolved file)
```
Release (only when the owner asks): as in homelab-ares' CLAUDE.md: CHANGELOG section in a PR, then a signed
tag (`git tag -s vX.Y.Z`) checked against `.github/allowed_signers`, pushed; verify from outside afterwards.
