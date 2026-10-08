# Changelog

All notable changes to homelab-helios are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

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
- Dependabot for the images, the Python tools and the Actions; patch and minor updates merge automatically
  once every required check passes; major updates wait for the maintainer.
- A release workflow that publishes a source archive, the SBOM, `SHA256SUMS` signed keylessly with cosign,
  and SLSA build provenance ([docs/verifying-releases.md](docs/verifying-releases.md)).

[Unreleased]: https://github.com/HoneyBearTech/homelab-helios/commits/main
