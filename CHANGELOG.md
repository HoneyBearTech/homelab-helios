# Changelog

All notable changes to homelab-helios are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Upgrading

- **Put the Dozzle certificate and key in `CONFIG_ROOT/dozzle/certs` before deploying this** (owned by root; the
  same pair on the Dozzle hub, which needs its own update: [docs/installing.md](docs/installing.md#dozzles-certificate)).
  Without them the Dozzle agent doesn't start. Once the agent has its pair, the hub reaches it only after it has
  the same one, so switch the agents and the hub one right after the other.
- **Move each app's data into its folder under `CONFIG_ROOT` before deploying this**, and **add `CONFIG_ROOT` to
  `.env`** (required; see `.env.example`). Never set it to a path inside `/var/lib/docker/volumes`
  ([docs/installing.md](docs/installing.md#where-data-lives)). With the whole stack stopped (`docker compose stop`:
  AURA, Kometa and ImageMaid mount each other's and Plex's folders), move each old location (wherever its setting
  pointed, a Docker volume's `_data` folder included) to its new folder, owned by `PUID:PGID` (every app here runs as
  that user):

  | Old location (setting) | New folder |
  | --- | --- |
  | `PLEX_CONFIG_PATH` | `CONFIG_ROOT/plex/config` |
  | `PLEX_CACHE_PATH` | `CONFIG_ROOT/plex/cache` (disposable: an empty folder will do) |
  | `PLEX_TRANSCODE_PATH` | `CONFIG_ROOT/plex/transcode` (scratch: an empty folder will do) |
  | `TAUTULLI_CONFIG_PATH` | `CONFIG_ROOT/tautulli/config` |
  | `AURA_CONFIG_PATH` (with its `auraassets`) | `CONFIG_ROOT/aura/config` |
  | `KOMETA_CONFIG_PATH` (with its `.env` and `aura`) | `CONFIG_ROOT/kometa/config` |
  | `IMAGEMAID_CONFIG_PATH` | `CONFIG_ROOT/imagemaid/config` |
  | `QUICKSTART_CONFIG_PATH` | `CONFIG_ROOT/quickstart/config` |

  On the same filesystem a move is instant (`mv`); across filesystems, copy with `cp -a` (keeps owners and modes) and
  remove the old folder once the stack runs from the new one. Every folder in the table must exist before the deploy,
  even if empty: Plex's cache is mounted with Compose's long syntax, which doesn't create a missing folder
  ([docs/quick-start.md](docs/quick-start.md) step 3 makes them all). Then drop the old settings from `.env` (they're no
  longer read) and keep the stack stopped until this is deployed. A deploy without `CONFIG_ROOT` stops at
  `docker compose config` and changes nothing. To keep transcodes on a separate fast disk, mount it at
  `CONFIG_ROOT/plex/transcode`.
- Backups taken with the old settings restore as they are: `scripts/restore.sh` puts each archive where
  `compose.yaml` mounts its container path now.

### Added

- `scripts/post-deploy-check.sh`: the check the server's pull agent (homelab-pull 0.5.0 or later, its `CHECK`
  setting) runs after each deploy. When `kometa/` or the `kometa` service in `compose.yaml` (its image included)
  changed since the commit the check last passed on, it validates Kometa's configuration with the real values
  (`--validate --validate-level full` in a one-off `docker compose run --rm --no-deps` container, stopped after
  `KOMETA_CHECK_TIMEOUT`, default 480 s), which CI can't do. A failure leaves the deploy running; the agent logs it
  as `failed:check`, which alerts, and retries it. Replaces the manual check after a merge that changes Kometa
  ([docs/kometa.md](docs/kometa.md#the-check-with-the-real-values-after-a-deploy)).
- A weekly Plex update watch (`.github/workflows/plex-update-watch.yml`, `scripts/plex_watch.py`), because
  Dependabot can't read any of Plex's image tags: while linuxserver.io has a newer Plex build than the one pinned (a
  new Plex version or a rebuild), it keeps one issue, "Plex update available", with the newer builds and the latest
  one's tag and digest, ready to pin. It never repeats itself, sends an optional alert to its own Discord webhook or
  ntfy topic (`PLEX_DISCORD_WEBHOOK`, `PLEX_NTFY_URL`; the Kometa watch's while those aren't set), and closes the
  issue once the pin is the newest build. A manual run can instead send just a test alert.

### Changed

- The smoke test runs a stack's own steps from `scripts/smoke-stack.sh` when that exists (`smoke_prepare` before the
  services start, `smoke_check` once they are healthy and again after the restore), gives a `*_SUBNET` setting a free
  address range, and leaves a service with Docker secrets out of the restore's "recreated with older settings" check.
  None of these is in use here; they keep the stacks' tooling the same.
- Kometa runs at 07:30 by default (`KOMETA_TIMES`, was 02:00), well after the nightly backup. A backup that
  runs long, as when a backup of the whole virtual machine loads the disk at the same time, kept Plex stopped
  past 02:00, and the Kometa run found none of its libraries and did nothing. **Set `KOMETA_TIMES=07:30` in
  `.env`** if yours has `02:00` (copied from `.env.example`): the default only applies when it's unset.
- Docs: a GPU host needs **Docker Engine 29.2 or later** and NVIDIA Container Toolkit 1.18 or later
  ([docs/installing.md](docs/installing.md#the-gpu-and-docker-292)). From 29.2 Docker serves `compose.gpu.yaml`'s
  `driver: nvidia` reservation through CDI (the toolkit's `nvidia-cdi-hook`, with `nvidia-cdi-refresh` keeping the
  spec current). On an older Engine it uses NVIDIA's runtime hook, and Plex loses the GPU at every
  `systemctl daemon-reload` (apt and unattended-upgrades run one): `nvidia-smi` in the container fails with "Failed
  to initialize NVML: Unknown Error" (NVIDIA container-toolkit issue #48) and Plex transcodes on the CPU. The docs
  give a check (`sudo systemctl daemon-reload`, then `docker exec plex nvidia-smi -L`). The compose files are
  unchanged apart from a comment.
- Every app's data moves to one layout under a new required setting, `CONFIG_ROOT` (the maintainer's decision,
  2026-10-15, the same in all the homelab stacks): each app's settings and database in `CONFIG_ROOT/<app>/config`,
  and its other folders beside it (Plex's `cache` and `transcode`). It replaces `PLEX_CONFIG_PATH`,
  `PLEX_CACHE_PATH`, `PLEX_TRANSCODE_PATH`, `TAUTULLI_CONFIG_PATH`, `AURA_CONFIG_PATH`, `KOMETA_CONFIG_PATH`,
  `IMAGEMAID_CONFIG_PATH` and `QUICKSTART_CONFIG_PATH`; container paths, the media library (`MEDIA_PATH`) and the
  backup labels are unchanged. `scripts/restore.sh` writes each archive to what the service mounts at that container
  path now, recreating a container made from an older `compose.yaml` or `.env` and creating a missing directory, as
  on homelab-atlas; the smoke test covers that path. A new test (`tests/test_settings.py`) checks that every
  setting is in `.env.example` and `docs/interfaces.md`, that each app's data comes from `CONFIG_ROOT/<app>/...`
  and that nothing mounts a named volume. `.env.example` now lists `UMASK` too.
- Docs: a warning never to point a path setting into `/var/lib/docker/volumes` nor keep app data in named Docker
  volumes. `docker volume prune`, `docker system prune --volumes` and Portainer's "remove unused volumes" delete
  every volume no container mounts as a volume, including one whose `_data` folder a service bind-mounts by path: a
  volume prune deleted a server's Plex database that way
  ([docs/installing.md](docs/installing.md#where-data-lives)).
- `scripts/backup.sh` and `scripts/restore.sh` take the pull agent's deploy lock before they stop anything and hold
  it until they finish, so a merge can't be deployed in the middle of a backup or a restore (the deploy's
  `docker compose up -d` would start a service while its data is being copied, and the archive of a database could
  be inconsistent). They wait up to 30 minutes for a deploy in progress, then fail without stopping anything; the
  agent skips its runs while they hold the lock. Where the agent has never run (CI, a development machine) they
  don't lock. `deploy_lock` in `scripts/lib.sh`, tested in `tests/test_deploy_lock.py`
  ([docs/installing.md](docs/installing.md#scheduled-backups)).
- Docs: the pull agent recreates Kometa by itself when a `kometa/` file changes (only the check with the real values
  is still run by hand) and removes unused images after each deploy; the roadmap records the move to `main`, the
  Passing and Silver badges and the parked rebuild rehearsal; the quick start no longer waits for a first release.
- Docs: the maintainer's server now follows `main` with a pull agent instead of running a release tag, so a merge
  deploys within about two minutes, Dependabot's automatic merges included. Rollback is a revert pull request; a
  server is held on a version by checking out that commit, which pauses the agent. Release tags stay as signed,
  verified snapshots ([docs/upgrading.md](docs/upgrading.md#following-main)).
- Dependabot's image rebuilds (the same tag moving to a new digest: a rebuild of the same app version, with newer
  base packages) now merge automatically once every required check passes, as on homelab-atlas. The rule merges only
  a pull request whose one changed file is `compose.yaml`, whose changed lines are all `image:` lines, and whose
  image tags stay the same.
- Tautulli is pinned by its linuxserver.io `version-<app version>` tag (`version-v2.18.2`) and socket-proxy by its
  bare version (`3.4.6`, as on the other homelab stacks) instead of their build tags (`v2.18.2-ls246`,
  `3.4.6-r0-ls101`). Dependabot reads a build tag's `-lsNNN` as a suffix that must match exactly, so it never
  proposed a new version or build of either; now it proposes both. The digests are unchanged, so the images are
  the ones pinned before, and Dependabot brings the newer builds in its own pull requests. Plex keeps its build tag:
  no Plex tag is one Dependabot can read, so Plex is updated by hand.

### Fixed

- **The Dozzle agent keeps the notification settings the Dozzle hub sends it in memory** (`/data` is a tmpfs now).
  It saves them to `/data`, which was part of its read-only root filesystem, so each time the hub started the agent
  logged "failed to save config: open ./data/notifications.yml: read-only file system" and "Could not remove cloud.yml
  on agent", and the hub "Failed to broadcast notification config to agent". The hub keeps these settings itself and
  sends them again each time it starts, so nothing is kept on disk or in the backups. The smoke test now starts a
  throwaway hub and checks that the agent takes its settings. Nothing to do on the host.

- `scripts/backup.sh` no longer leaves a service down when stopping it fails. A process that can't exit in time
  (stuck writing to a network share) made the stop fail while its container was still on its way down; the backup
  gave up, started the services again at once (Compose skipped the container, which still ran) and the service stayed
  stopped once it exited, as `restart: unless-stopped` doesn't restart after a stop. The rest of the backup and the
  copy off the host were never made. Now the backup waits up to `BACKUP_STOP_WAIT` seconds (default 120) for the
  container to exit and carries on; if it still runs then, the backup fails and waits once more before starting
  anything. Every service that was running when the backup began must be running again at the end, or the backup
  fails and names it (the scheduled backup reports that to the push monitor).
- `scripts/restore.sh` stops a service that bind-mounts a folder inside a mount it restores, and starts it again
  afterwards. Such a container kept seeing the folder the restore had replaced, deleted, until it restarted (found on
  homelab-hyperion). Here that is ImageMaid, which reads Plex's folder, and AURA and Kometa, which mount each other's:
  restoring only Plex left ImageMaid on the deleted folder, and restoring only Kometa or AURA did the same to the
  other. A full restore was not affected (every one of them is restored and restarted). The smoke test now checks it
  with a test container that follows another service's folder, and by restoring Plex, AURA and Kometa each on its own.

### Security

- **The Dozzle agent no longer accepts the certificate built into every Dozzle image.** Dozzle v11.3.4 warned that
  the agent used that pair, which every copy of the image ships, so anyone on the LAN with a Dozzle image could
  connect to its port and read every container's log or control Docker through it. The agent now reads a pair of
  its own, shared only with the homelab's Dozzle hub, from Docker secrets in `CONFIG_ROOT/dozzle/certs` (owned by
  root, never committed or backed up), and doesn't start without it. The smoke test makes a throwaway pair and
  checks that the agent accepts a hub with it and refuses one with the built-in pair
  ([docs/installing.md](docs/installing.md#dozzles-certificate)).
- The Dozzle agent moves to v11.3.4 (built with Go 1.27.3), which fixes the image scan's Go `crypto/x509` finding
  (CVE-2026-111943) in v11.3.2. Dependabot didn't propose it: it holds back Docker Hub releases for a few days
  after they're published, and both v11.3.3 and v11.3.4 were still that new at its last run.

## [0.3.0] - 2026-10-14

The backup scripts, smoke test and CI are aligned with homelab-ares, the template for the homelab stacks, and every
service is hardened as there. The backup's systemd units stay as they are (they got the best-effort I/O class in
0.2.1, so they don't need re-installing).

### Upgrading

- Every service now runs without Linux capabilities and with `no-new-privileges`; Plex and Tautulli add back only
  the few their init needs, from Docker's default set (docs/security.md#hardening). Their data must be owned by
  `PUID:PGID`, and the other services' data by the user they run as: a service that fails with "permission
  denied" (`EACCES`) after the upgrade usually has data with an unexpected owner. Plex's GPU is unchanged (a
  device reservation, in `compose.gpu.yaml`); check hardware transcoding after the upgrade, since CI has no GPU.

### Added

- Each backup also holds `NETWORKS`, the address range and gateway of every network the stack uses but doesn't
  create (none today: Compose creates both of the stack's networks, so it holds only its header), and `VERSION`,
  the checkout's `git describe`, so a backup says which release it was taken with. The smoke test checks
  `VERSION`, and `NETWORKS` for any network the stack doesn't create.
- CI and the weekly image scan log in to Docker Hub with a read-only token when the repository has one
  (`DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`), so their pulls don't hit the runners' shared anonymous limit; without
  it they pull anonymously, as before. The smoke test pulls every image first and logs out before any container
  starts (GOVERNANCE.md).

### Changed

- `scripts/backup.sh` and `scripts/restore.sh` check every `org.honeybeartech.helios.backup.exclude` label before
  anything stops: each path must be a plain path strictly inside one of the service's data mounts, without `..`
  or a pattern character (`*?[\`); otherwise both fail with every service still running. Plex's and Kometa's
  labels pass unchanged, and back up exactly the same data as before. `restore.sh` also lists, for each mount,
  the paths it leaves in place.
- The smoke test owns each throwaway data directory by `PUID:PGID` with mode 0755, as the directories are on a
  host, instead of making them writable by everyone, so a service that needs more than that fails in CI rather
  than at a deploy. It also checks that every backup has a `NETWORKS` file.
- `docs/quickstart.md` (Kometa Quickstart, the on-demand tool) is now `docs/kometa-quickstart.md`, so it isn't
  mistaken for the stack's quick start (`docs/quick-start.md`).

### Security

- Every service drops every Linux capability (`cap_drop: [ALL]`) and runs with `no-new-privileges:true`. Plex adds
  back `CHOWN`, `DAC_OVERRIDE`, `SETUID`, `SETGID` and `KILL`, Tautulli `CHOWN`, `SETUID`, `SETGID` and `KILL`;
  the others none.
- AURA, Kometa, Kometa Quickstart, ImageMaid, the Dozzle agent and autoheal run with a read-only root filesystem
  (`/tmp` in memory where the image writes temporary files), as socket-proxy already did. Plex and Tautulli keep a
  writable one: LinuxServer.io's init would ignore `PUID`/`PGID` on a read-only root.
- The policy check enforces it, as in homelab-ares: new rules `no-new-privileges` and `cap-drop`; `cap-add` now
  fails only on a capability outside Docker's default set; new rule `devices` (no host device mapped into a
  container; a GPU reservation under `deploy.resources` is allowed).

## [0.2.2] - 2026-10-13

A pinned Dozzle agent joins the stack, Kometa runs about two hours shorter on most nights and checks TLS
certificates again, it stops unmonitoring shows and movies, and the NVIDIA driver stays out of unattended upgrades.

### Added

- A Dozzle agent (`dozzle-agent`: `dozzle agent`, port 7007, 11.3.2, the hub's version) for the homelab's Dozzle
  hub on another host, which shows every host's logs in one web UI. It mounts the Docker socket read-only, an
  allowed `docker-socket` exception; keep port 7007 on the LAN. A host that already runs a container named
  `dozzle-agent` outside the stack must remove it before `docker compose up -d`.
- `deploy/apt/51unattended-upgrades-nvidia`, which keeps the NVIDIA driver out of unattended upgrades. An
  unattended driver update without a reboot left Plex unable to start with the GPU ("driver/library version
  mismatch") until the host was rebooted. The rebuild guide installs it and the DKMS driver it assumes; update the
  driver by hand and reboot straight after.

### Changed

- Kometa applies the TV Shows overlays (resolution and audio badges on shows, seasons and episodes) on Sundays
  instead of every day, as Anime and Kid's TV Shows already did. Walking every episode for two badges was more
  than half of each nightly run (about 1 h 55 min); a new episode or season now gets its badges within a week.

### Fixed

- Kometa no longer unmonitors shows in Sonarr or movies in Radarr. With `monitor_existing: true`, Kometa
  applied its `monitor` setting (`none` for Sonarr, `false` for Radarr, meant for items it adds) to every
  existing item its collections matched, so airing shows stopped being searched for. `monitor_existing` is now
  `false` for every Radarr and Sonarr connection, so Kometa leaves monitoring alone.
- Kometa's Refresh Metadata collections no longer fail when nothing was released or aired in the last 7 days.
  Each library with nothing new logged `Plex Error: No Items found in Plex`, was reported as a Kometa Failure
  and sent an error notification, about six every night; with `ignore_blank_results` it's a warning.
- The Kometa upstream watch's Discord alert is delivered: Discord refused it with 403 (Cloudflare error 1010)
  because it carried urllib's default `User-Agent`. Alerts now name the watch in their `User-Agent`.

### Security

- Kometa checks TLS certificates again. `settings.verify_ssl: false` turned certificate checks off for every
  HTTPS request Kometa made, including the ones that carry the TMDb, OMDb and MDBList API keys; both
  `verify_ssl: false` lines are gone, so the default (verify) applies. Plex, Tautulli, Radarr and Sonarr are
  reached over plain HTTP on the LAN, so nothing else changes.

## [0.2.1] - 2026-10-10

Backups stop each service for a fraction of the time, and the GitLab mirror updates `main` again.

### Fixed

- The GitLab mirror job fetches into a bare repository: git refuses to fetch into the checked-out branch of a
  non-bare one, so the job couldn't update `main`.
- A backup copies a service's data several times faster, so the service is back sooner: the container that
  archives it no longer has Docker's log driver also write the whole archive into its log, and the systemd unit
  runs at the lowest best-effort I/O priority instead of the idle class, which waited behind every other disk user
  on the host. On Helios the first scheduled backup copied Plex at 5 to 10 MB/s, keeping it stopped for 35
  minutes, instead of the 90 MB/s measured by hand.

## [0.2.0] - 2026-10-10

Scheduled backups copied off the host, without what the services re-create, and shorter downtime while a
backup runs.

### Added

- Scheduled backups copied off the host: `scripts/scheduled-backup.sh` takes a backup, copies it to
  `BACKUP_REMOTE` with rsync (`SHA256SUMS` last, so a cut-off copy is refused on restore), keeps the newest
  `BACKUP_KEEP` (3) here and `BACKUP_REMOTE_KEEP` (14) there, and reports to an Uptime Kuma push monitor. Settings
  in the optional, gitignored `backup.env` (template `backup.env.example`); systemd user units in `deploy/systemd/`
  run it nightly at 01:00, before Kometa's run ([docs/installing.md](docs/installing.md#scheduled-backups)).
- The `org.honeybeartech.helios.backup.exclude` label: paths inside a data mount that backups leave out and
  restores leave in place. Plex leaves out its artwork (`Metadata`) and preview thumbnails (`Media`), Kometa its
  downloaded `assets/`; the services re-create them after a rebuild
  ([docs/rebuilding.md](docs/rebuilding.md#what-the-backup-doesnt-bring-back)).

### Changed

- `scripts/backup.sh` stops one service at a time, only while it copies that service's data, and compresses the
  copy after starting the service again (with pigz when it's installed), instead of stopping the whole stack for
  the whole backup: Plex is down for minutes, not hours. The archives and `scripts/restore.sh` are unchanged.

## [0.1.0] - 2026-10-09

The first release: the Helios stack (Plex, Tautulli, AURA, Kometa and ImageMaid, with autoheal, and Kometa
Quickstart as an on-demand tool) as a Compose file, every image pinned by version tag and digest for
`linux/amd64`, with Kometa's configuration, health checks, backups and release signing around it.

### Added

- `.gitlab-ci.yml` for the copy of the repository on the maintainer's self-hosted GitLab. GitHub stays the
  project's home and its Actions the required checks; on GitLab a scheduled job mirrors `main` and the tags from
  GitHub (fast-forward only, with a project access token in a masked, protected CI/CD variable), and every
  commit that arrives gets the checks that need no Docker daemon: ruff, yamllint, shellcheck, the unit tests
  with the coverage floor, gitleaks over the whole history, actionlint and the Compose policy check.
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

### Security

- First triage of the image scan, recorded in [docs/dependencies.md](docs/dependencies.md#current-findings).
  Every image is on its newest release, so no update fixes anything yet. AURA's critical Next.js finding isn't
  reachable, because AURA doesn't use `next/og`. Most of ImageMaid's 525 findings are in packages it never
  uses; Pillow is reachable only in its `OVERLAYS_ONLY` mode, which is off by default.

[Unreleased]: https://github.com/HoneyBearTech/homelab-helios/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/HoneyBearTech/homelab-helios/compare/v0.2.2...v0.3.0
[0.2.2]: https://github.com/HoneyBearTech/homelab-helios/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/HoneyBearTech/homelab-helios/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/HoneyBearTech/homelab-helios/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/HoneyBearTech/homelab-helios/releases/tag/v0.1.0
