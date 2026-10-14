# homelab-helios

The Docker Compose stack for Helios, the owner's homelab media server (Ubuntu 24.04, amd64, a VM with an NVIDIA
GPU passed through): Plex, Tautulli, AURA (MediUX artwork), Kometa and ImageMaid, with autoheal and a Dozzle agent (and Kometa Quickstart as an on-demand tool), every image pinned by tag and digest so
the server can be upgraded and rebuilt from this repository. Helios runs the stack (`compose.yaml` +
`compose.gpu.yaml`) from a checkout of `main` that a pull agent deploys (see Deploys below); its nightly backups go
off the host.
homelab-ares is the template for the homelab stacks: tooling that isn't specific to this host's services (checker,
backup scripts, smoke test, workflows) is kept the same as ares'; a change here that isn't about this host's
services goes to ares too (owner 2026-10-13).

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

The sibling repos `~/GitHub/homelab-ares`, `~/GitHub/homelab-atlas`, `~/GitHub/homelab-deimos` and
`~/GitHub/homelab-hyperion` follow the same pattern; ares is the template for tooling, workflows and policy files
(above). This repo was bootstrapped from deimos (the closest match: an NVIDIA GPU, a media library on a network
share). What stays specific to helios: the `tools` profile (`tool_profiles`/`COMPOSE_PROFILES` in `lib.sh`, the
never-started-tool skip in `backup.sh`, `--profile tools` in the workflows, Makefile and `.gitlab-ci.yml`),
everything Kometa, the amd64 runners, `compose.gpu.yaml`, the NVIDIA apt hold, auto-merge of majors and the 01:00
backup timer.

## This repo is public
- No hostnames, IP addresses, internal or public domains, host paths, NFS exports, Portainer stack names, Plex
  server names, Plex account names or personal email addresses in anything committed: code, compose, the
  docs, examples, tests, commit messages. Host facts live only in the Chronos notes. Examples use
  placeholders (`/srv/appdata`, `/srv/media`, `example.com`, `homelab-helios_`).
- Commit as `31805425+HoneyBearTech@users.noreply.github.com` (set as this repo's `user.email`), with
  `git commit -s` for the DCO sign-off; commits and tags are SSH-signed.
- No secrets: Plex's server token, the Plex tokens Tautulli, AURA, Kometa and ImageMaid hold, AURA's MediUX
  token, Kometa's API keys (in the `.env` in its data directory) and logins stay in the
  services' data on the host, never in `compose.yaml`, `.env` or the `*.example` files. A secret a service can
  only take from its environment gets its own gitignored `<service>.env` (`env_file`) with a committed
  `<service>.env.example`: Plex's one-time `PLEX_CLAIM` goes in `plex.env`. `.gitignore` covers `.env`, keys,
  certificates, `appdata/`, `data/`, `media/`, `transcode/`, `backups/`; extend it rather than work around it.
- Keep the repo on track for OpenSSF Baseline Levels 1 and 2 and the Best Practices Passing and Silver
  badges (project 15291). If a change would break a met criterion (for example unpinning an image or an
  Action, adding a workflow without `permissions:`, or dropping the coverage floor), say so before making it.

## Rules for the stack
- **Every image is pinned as `name:tag@sha256:<digest>`.** Never `latest`, never tag-only. Dependabot
  (`docker-compose` ecosystem) updates tag and digest together. linuxserver.io images use their `version-<app
  version>` tag (socket-proxy its bare version), never the `-lsNNN` build tag: Dependabot can't follow those. Plex
  is the exception: no Plex tag is one Dependabot can read (its version carries a commit hash), so it keeps its
  build tag and is updated by hand; a weekly watch (`scripts/plex_watch.py`, one issue, owner 2026-10-14) stands in
  for Dependabot. Patch, minor and major updates, and image rebuilds (same tag, new digest; owner 2026-10-14),
  auto-merge once the required checks pass (Plex included: it can't touch the media; majors too, owner 2026-10-08).
  Every merge deploys, the automatic ones included, majors too (see Deploys): a major can migrate a service's data
  one way and now reaches Helios unattended, with only the nightly backup behind it.
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
- **Nightly backups leave out what the services re-create** (owner 2026-10-09): paths inside a data mount listed in
  a service's `org.honeybeartech.helios.backup.exclude` label aren't archived, and `restore.sh` leaves them in
  place: Plex's `Metadata` and `Media` (artwork, preview thumbnails: 65 of its 82 GB on Helios) and Kometa's
  `/config/assets`. Each value must be a plain path strictly inside one of the service's data mounts (no `..`, no
  `*?[\`): `check_excludes` in `lib.sh` fails the backup and the restore before anything stops otherwise. Each
  backup also records `NETWORKS` (external networks' address ranges; none here) and `VERSION` (`git describe`).
  `backup.sh` stops one service at a time, only while it copies that service's data, and
  compresses after starting it again (gzip of Plex's 12 GB of databases takes ~14 min on Helios, the copy ~2).
  `scripts/scheduled-backup.sh` + `deploy/systemd/` run it nightly at 01:00 (before Kometa's 02:00 run) and copy it
  off the host; the backup server's name lives only in the host's `~/.ssh/config` and `backup.env`, never here.
- **Every service is hardened** (`x-hardened`: `cap_drop: [ALL]`, `no-new-privileges:true`) and adds back only
  the capabilities from Docker's default set its image needs, each with a comment saying why (Plex: `CHOWN
  DAC_OVERRIDE SETUID SETGID KILL`; Tautulli: `CHOWN SETUID SETGID KILL`; the rest none; docs/security.md#hardening).
  Prove a new one by starting the image without it (LinuxServer.io's s6 init needs `KILL` to stop its app cleanly).
  Every service but Plex and Tautulli has a read-only root (`read_only: true`, `tmpfs` for what the image writes);
  LinuxServer.io's init ignores `PUID`/`PGID` on a read-only root, so those two stay writable.
- **No privileged containers, capabilities beyond Docker's defaults, host network/PID, device mappings or Docker
  socket mounts** unless the service carries `org.honeybeartech.helios.allow.<rule>: "<reason>"` and the owner agreed (Plex runs on the
  stack's network, publishing only 32400: owner 2026-10-07; it ran in host mode before the cutover). `scripts/check_compose.py` enforces it in CI
  and in the release workflow. Policy exceptions in use (each agreed by the owner): `socket-proxy` (`docker-socket`:
  filters the API down to list/inspect/restart/stop for autoheal, internal network, no port), `autoheal` (`latest`:
  the image's only maintained tag), `dozzle-agent` (`docker-socket`, read-only mount; an agent for the homelab's
  Dozzle hub on another host, port 7007, owner 2026-10-13). Don't add more without the owner agreeing.
- **Every service has a health check** and the `autoheal: "true"` label. autoheal (`willfarrell/autoheal`)
  behind `lscr.io/linuxserver/socket-proxy` (read-only socket, internal `docker-proxy` network) is part of the
  first `compose.yaml`, exactly as on homelab-atlas/ares (owner 2026-10-07); its webhook URL goes in the
  gitignored `autoheal.env`. The smoke test checks autoheal restarts a service that turns unhealthy.
- **Never change the live server** (Helios) without the owner asking: merges only as **Merging** says, no
  `docker compose up`, no edits to service data, Plex libraries or settings, or Portainer stacks. Read-only inspection
  (`docker ps`, `docker inspect`) only when asked (host quirks for doing so are in the Chronos Architecture note).
- Every setting goes through `.env` (`${VAR:?…}` in compose when required) and is listed in `.env.example`
  and `docs/interfaces.md`.
- **Container paths, image family and ports are load-bearing**: Plex stores library paths (`/media/...`) in its
  database, and the LinuxServer.io image family (Plex, Tautulli) lays out `/config` its own way; players, Tautulli, plex-director-mcp and the
  reverse proxy reach the services by their published ports. Adopt the existing data and keep paths, image
  family and ports the same; see the cutover plan in Chronos.

## Kometa
Kometa's configuration is in the repo (`kometa/`, mounted read-only over `/config/<name>` with
`KOMETA_READ_ONLY_CONFIG`; the Decisions-Log entries from 2026-10-08), validated by the required `CI / Kometa config`
check (`scripts/kometa-validate.sh`), and watched weekly (`scripts/kometa_watch.py`, one issue; docs/kometa.md).
- **Secrets and host facts in Kometa's YAML are placeholders**: `<<UPPER_SNAKE>>`, which Kometa fills from
  the `KOMETA_<UPPER_SNAKE>` environment variable (`<<lower_snake>>` doesn't match, and an unmatched
  placeholder silently becomes empty). That covers tokens, API keys, Plex's URL, notification URLs and
  Radarr/Sonarr addresses and root folders. The values go in `.env` in Kometa's data directory (Kometa loads
  it itself), never in the repo. Every file in `kometa/` is linked from `config.yml` and mounted in compose
  (the placeholder test checks both). Kometa reserves some `KOMETA_*` names (`KOMETA_PLEX_URL`/`_TOKEN`).
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
- **Kometa's validation is a required check.** Dependabot's Kometa updates (majors too) auto-merge, so the
  validation runs as an always-running job (never path-filtered: a skipped required check blocks the PR).
- Reviews of Kometa's configuration (optimization findings) are private planning: they go in Chronos, not
  `docs/`.

## Deploys (owner's decision 2026-10-14)
- **A merge to `main` deploys.** A pull agent on Helios (systemd user timer `homelab-pull@helios`, from the owner's
  private homelab-ops repo; rolled out host by host, see Chronos) fetches `main` about every 90 s. When it moved,
  the agent fast-forwards the checkout and runs `docker compose config --quiet`, `docker compose pull` and
  `docker compose up -d --remove-orphans --wait`: a merge is live within about two minutes. It refuses local
  changes and non-fast-forward history, and moves the checkout back if config or pull fails.
- **Rollback is a revert PR**, deployed the same way. A revert doesn't undo a data migration: then the backup and
  `scripts/restore.sh` are the way back, with the owner.
- **Pinning by hand**: the owner checks out another commit or tag on the host; the agent pauses until the checkout
  is on `main` again. Release tags stay as signed, verified snapshots; they no longer drive deploys.
- **Kometa**: the agent's `up -d` doesn't recreate Kometa when only `kometa/` changed (single-file mounts keep the
  old file), and it doesn't run `--validate --validate-level full` with the real values. After a merge that changes
  `kometa/` or Kometa's image, the owner runs both on the host (docs/upgrading.md#following-main).

## Stack
- Docker Compose v2 (`compose.yaml`; the GPU in `compose.gpu.yaml`, added on the host via `COMPOSE_FILE`), upstream images: `lscr.io/linuxserver/plex` (with
  `VERSION=docker`, so it never self-updates), `lscr.io/linuxserver/tautulli`, `ghcr.io/mediux-team/aura`,
  `kometateam/kometa` and `kometateam/imagemaid` (release tags, not `nightly`/`develop`), autoheal +
  socket-proxy, a Dozzle agent (`amir20/dozzle`, `command: agent`, on the hub's version: owner 2026-10-13);
  `kometateam/quickstart` (release tags) as a **tool** in the `tools` profile: not started by
  `docker compose up -d`, `restart: "no"`, port 7171 on the LAN, no login (owner 2026-10-08:
  config editor only, never its own Kometa/ImageMaid runs or self-updater). Tooling must see the tools: the
  workflows and `make check`/`config` pass `--profile tools`, the scripts get `COMPOSE_PROFILES` from `lib.sh`.
  Not in this repo: Homebox, InvenTree (and its Caddy), TitleCardMaker, Watchtower, Diun, the
  Argus agent and Argus' Loki, the Portainer agent.
- Tooling (kept the same as homelab-ares'): `scripts/check_compose.py` (Python, standard library only:
  policy check + CycloneDX SBOM), `scripts/backup.sh`, `restore.sh`, `scheduled-backup.sh`, `smoke-test.sh`, `lib.sh` (bash,
  must run on macOS' bash 3.2; `scheduled-backup.sh` also with macOS' openrsync, so no `--chmod`); ruff (`select = ["ALL"]`), yamllint, shellcheck, pytest + coverage (90 % branch floor),
  pip-tools for the hash-pinned `requirements-dev.txt`. CI-only: actionlint, gitleaks, CodeQL, Scorecard,
  dependency review, DCO, Trivy image scan, Dependabot auto-merge (patch, minor, major, rebuilds). CI and the image scan
  log in to Docker Hub with the read-only `DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN` secrets when they are set
  (anonymous pulls otherwise; fork PRs get no secrets); the smoke job pre-pulls every image and logs out before
  any container starts (GOVERNANCE.md).
- GitLab copy: the owner's self-hosted GitLab (CE, LAN only; host facts in Chronos) holds a mirror. GitHub stays
  the home (OpenSSF badges, Scorecard, Dependabot, releases); every change goes to GitHub as a PR, never to
  GitLab. `.gitlab-ci.yml` mirrors GitHub on a schedule (fast-forward only, `MIRROR_TOKEN` CI/CD variable) and
  re-runs the daemon-free checks; smoke test and Kometa check stay GitHub-only (owner 2026-10-08).
- Releases (`release.yml`, on a `v*.*.*` tag): policy check, source archive, CycloneDX SBOM,
  `SHA256SUMS` signed with cosign keyless, SLSA provenance, GitHub Release from the tag's `CHANGELOG.md`
  section. No images are built or published.

## Conventions
- `CHANGELOG.md` (Keep a Changelog): add to "Unreleased" with every user-visible change.
- Docs in `docs/` change in the same PR as the behaviour; anything not built yet is marked **Planned**.
- Workflows: top-level `permissions: contents: read` (Scorecard: `read-all`), raise per job; actions pinned by
  full SHA with a version comment; untrusted `${{ github.event.* }}` only through `env:`.
- Required checks in the `main` ruleset: `CI / Checks + tests`, `CI / Stack smoke test`, `CI / Kometa config`, DCO sign-off,
  Dependency review, CodeQL's Analyze (python) / Analyze (actions). Don't rename those jobs.
- **Merging (owner's decision 2026-10-14):** Claude opens a PR for every change. A merge deploys (see Deploys),
  so Claude merges once every required check is green (the owner's standing permission, 2026-10-14) and
  then says that it merged and that it's deploying to Helios. It asks first when the deploy needs something on
  the server (a new `.env` setting, a data migration without a recent good backup, an update this file says
  waits for the owner) or the server isn't healthy, and never turns on auto-merge (`gh pr merge --auto`)
  without the owner's OK. Never bypass a check or the ruleset.
  Dependabot's patch, minor and major updates and image rebuilds still auto-merge through
  `dependabot-auto-merge.yml` once every required check passes, so they now deploy unattended, majors included;
  Plex is pinned by hand. Keeping that auto-merge (above all for majors) is the owner's call: don't change
  `dependabot-auto-merge.yml` without it.

## Commands
```sh
make test     # checker tests + coverage floor (no Docker, no network)
make lint     # ruff check, ruff format --check, yamllint --strict, shellcheck -x
make check    # docker compose config --format json | scripts/check_compose.py  (needs .env and compose.yaml)
make smoke    # scripts/smoke-test.sh: throwaway project, healthy, backup/restore round trip, scheduled backup (needs Docker)
make config   # docker compose config (resolved file)
make kometa   # scripts/kometa-validate.sh: kometa/ against the pinned Kometa + its schemas (needs Docker, network)
```
Release (only when the owner asks): as in homelab-ares' CLAUDE.md: CHANGELOG section in a PR, then a signed
tag (`git tag -s vX.Y.Z`) checked against `.github/allowed_signers`, pushed; verify from outside afterwards.
