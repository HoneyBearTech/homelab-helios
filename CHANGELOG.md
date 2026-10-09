# Changelog

All notable changes to homelab-helios are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Kometa Quickstart (`kometateam/quickstart`), a web UI for building and validating Kometa configurations, as a
  tool started on demand: it is in the `tools` profile, so `docker compose up -d` doesn't start it and it isn't
  restarted after a reboot (`docker compose --profile tools up -d quickstart`). It publishes 7171 for the LAN
  and has no login; its data (`QUICKSTART_CONFIG_PATH`) holds the tokens entered in it
  ([docs/quickstart.md](docs/quickstart.md)). The policy check, the image scan, the release SBOM, backups,
  restores and the smoke test all include the tools; a backup skips a tool that has never been started.
- `kometa/`: Kometa's configuration (`config.yml` and the four collection files it links), with every secret and
  host fact as a `<<UPPER_SNAKE>>` placeholder that Kometa fills from `KOMETA_<UPPER_SNAKE>`;
  `kometa.env.example` lists them all. A test fails the build on any value under a credential, address or path
  key that isn't such a placeholder, on a placeholder name Kometa reserves for its own settings, and on a file in
  `kometa/` that `config.yml` doesn't link. The collection files that only tag or refresh items set
  `sync_mode: append`, which Kometa requires for them.
- [docs/kometa.md](docs/kometa.md): Kometa's placeholders and `.env`, the CI check, the weekly upstream watch and
  the safe upgrade path; `docs/upgrading.md` checks Kometa's configuration with the real values before starting it.
- A weekly Kometa upstream watch (`.github/workflows/kometa-upstream-watch.yml`, `scripts/kometa_watch.py`): when
  Kometa has a release newer than the pinned one, or `kometa/` doesn't validate against the latest, it keeps one
  issue, "Kometa upstream changes", up to date with the validation against the latest release, the release-note
  bullets that name something our configuration uses, and the diff of the Kometa defaults it references. Unchanged
  findings edit nothing; new ones update the issue with one comment and an optional alert (`NTFY_URL`,
  `DISCORD_WEBHOOK` secrets); it closes once the pin is the latest release again. `scripts/kometa-validate.sh`
  takes `KOMETA_IMAGE` to validate against another image.
- CI job "Kometa config" (`scripts/kometa-validate.sh`, `make kometa`): validates `kometa/` with the Kometa image
  pinned in `compose.yaml` and the JSON schemas from the same release, with dummy values for the placeholders.
  It fails on a schema error, when Kometa gives no result (it exits 0 without network), and on keys the schema
  doesn't know (Kometa itself only reports those). Broken fixtures prove it fails.
- Kometa reads `kometa/` from the checkout: each file is mounted read-only over `/config/<name>`, with
  `KOMETA_READ_ONLY_CONFIG` so Kometa never tries to rewrite `config.yml` (without it, a missing setting stops the
  run). Its secrets go in `.env` in its data directory, which Kometa loads itself, so they stay out of the
  container's environment. After a change to `kometa/`, recreate the container (docs/upgrading.md).
- `compose.yaml`: Plex, Tautulli, AURA, Kometa and ImageMaid, with autoheal behind a filtering socket proxy.
  Every image is pinned by tag and digest for `linux/amd64`, every service has a health check and the `autoheal`
  label, and none of them is touched by a host auto-updater (`com.centurylinklabs.watchtower.enable: "false"`).
  Plex runs the version in its image (`VERSION=docker`) on the stack's network with only 32400 published.
  AURA, Kometa and ImageMaid run as `PUID:PGID`.
- `compose.gpu.yaml`: the NVIDIA GPU for Plex as a device reservation, added on the host with `COMPOSE_FILE`.
- `plex.env.example` for Plex's one-time claim token; `IMAGEMAID_SCHEDULE`, `KOMETA_TIMES` and the data paths in
  `.env.example`.
- `scripts/backup.sh` leaves a mount that lies inside another one (Plex's cache inside its `/config`) out of the
  outer archive, and `scripts/restore.sh` leaves it in place; the smoke test can seed a throwaway data directory
  from `tests/smoke/` (a placeholder `config.yml` for Kometa).
- Documentation: quick start, installing, upgrading, rebuilding, architecture, interfaces, security
  requirements, assurance case, dependencies, roadmap and verifying releases.
- `.env.example` with the settings the stack is expected to read, `autoheal.env.example` for autoheal's optional
  webhook, and a `.gitignore` that keeps settings,
  service data, media, backups and keys out of the repository.
- Project policies (`SECURITY.md`, `CONTRIBUTING.md`, `GOVERNANCE.md`, `SUPPORT.md`, `CODE_OF_CONDUCT.md`),
  `CODEOWNERS`, issue and pull request templates.
- `scripts/check_compose.py`: the stack's policy check (every image pinned as `name:tag@sha256:<digest>`, no
  `latest`, no build, nothing privileged, no added capabilities, host network or PID namespace, no Docker
  socket mount, a health check on every service, unless a service's `org.honeybeartech.helios.allow.<rule>`
  label gives the reason), and the CycloneDX SBOM of the images for releases; tests with a 90 % branch-coverage
  floor.
- `scripts/backup.sh` and `scripts/restore.sh`: back up every service's read-write data mounts and the
  settings files with a manifest and checksums (readable only by the user who ran it), and restore them after
  verifying the checksums and asking first. Paths in a service's `org.honeybeartech.helios.backup.skip` label
  (the media library, Plex's cache and transcode directory, logs) are never archived, and a restore refuses to write them.
  `scripts/smoke-test.sh` starts the stack with throwaway settings, waits until every service is healthy, runs a
  backup and restore round trip and checks that excluded paths are left alone.
- CI on every change: ruff, yamllint, shellcheck, actionlint, gitleaks over the whole history, the checker's
  tests, the policy check and the smoke test on an amd64 runner. CodeQL,
  OpenSSF Scorecard, dependency review, a DCO check and a weekly image scan (Trivy, `linux/amd64`) also run.
- Dependabot for the images, the Python tools and the Actions; patch, minor and major updates merge
  automatically once every required check passes. A merge never deploys: a major version's release notes are
  read before the redeploy ([docs/upgrading.md](docs/upgrading.md)).
- A release workflow that publishes a source archive, the SBOM, `SHA256SUMS` signed keylessly with cosign,
  and SLSA build provenance ([docs/verifying-releases.md](docs/verifying-releases.md)).

[Unreleased]: https://github.com/HoneyBearTech/homelab-helios/commits/main
