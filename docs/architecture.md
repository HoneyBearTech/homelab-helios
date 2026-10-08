# Architecture

homelab-helios is the Docker Compose definition of **Helios**, a homelab media server: Plex, which streams the
media library to the household's players, with Tautulli watching what Plex does, and AURA, Kometa and
ImageMaid managing its artwork, collections and metadata. Helios is an Ubuntu 24.04 virtual machine on amd64 with an NVIDIA GPU passed through for Plex's hardware
transcoding. The repository holds configuration, not application code: the services run from their upstream
images, pinned by digest.

## Services

| Service | Image source | Role |
| --- | --- | --- |
| Plex Media Server | LinuxServer.io | Indexes the media library and streams it to Plex apps, transcoding on the GPU (NVENC/NVDEC) or the CPU |
| Tautulli | LinuxServer.io | Watches Plex: who played what, when, and how; history, statistics and notifications |
| AURA | MediUX's own image | Browses MediUX artwork sets and applies them to Plex: saves artwork next to the media, or writes sets for Kometa to apply |
| Kometa | the project's own image | Once a day, builds collections and overlays in Plex and applies artwork and metadata, including the sets AURA writes for it |
| ImageMaid | Kometa's project | Removes images Plex no longer uses from Plex's data directory, to keep it from growing |
| Kometa Quickstart | Kometa's project | A tool, started on demand: a web UI for building and validating Kometa configurations ([quickstart.md](quickstart.md)) |
| autoheal | the project's own image | Restarts any service whose health check fails, and can post a notice to a webhook (Docker on its own only restarts a container that exits) |
| socket-proxy | LinuxServer.io | Gives autoheal a filtered view of the Docker API (list, inspect, restart and stop containers only) on an internal network |

Every service has a health check; autoheal acts on it.

Other services on the same host (an inventory app, a title-card generator, monitoring agents and log storage, Docker management)
come from their own projects; this stack doesn't include or manage them.

## Actors and actions

| Actor | Does |
| --- | --- |
| Maintainer | Merges pull requests, tags releases, runs `git pull` / `docker compose up -d` on the host, configures each service in its web UI |
| Dependabot | Opens a pull request when an image (tag and digest), a check tool or an Action has a new version; patch, minor and major updates are auto-merged once the checks pass |
| CI | Lints, scans for secrets, tests the checker, resolves the Compose file, enforces the policy and smoke-tests the stack on amd64 (without a GPU) on every pull request |
| Release workflow | On a version tag: checks the policy, writes the SBOM, signs the checksums, publishes the GitHub Release |
| Household viewers | Play media through Plex apps on the LAN, and from outside it if Plex's remote access is on |
| plex.tv | Signs viewers in, and relays or brokers connections from outside the LAN |
| Other tools | Read Tautulli's or Plex's API (optional) |

## Data flow

```
Plex apps (LAN, or remote if it's on) ──▶ Plex :32400
Plex ◀──account, sign-in, remote access──▶ plex.tv

Plex ──read/write──▶ media library (network share or local disk)
Plex ──NVIDIA runtime──▶ GPU
Plex ──scratch files──▶ transcode directory

Tautulli ──API──▶ Plex
autoheal ──internal network──▶ socket-proxy ──read-only socket──▶ Docker (restarts unhealthy services)
AURA ──API──▶ Plex · MediUX;  AURA ──artwork──▶ media library, Kometa's config
Kometa ──API──▶ Plex · TMDb and other metadata sources;  Kometa ◀──artwork sets── AURA
ImageMaid ──read/write──▶ Plex's data directory (removes unused images)
LAN browsers ──HTTP(S) via reverse proxy──▶ Tautulli UI · AURA UI
```

Each service keeps its settings and database in its own data directory (see
[interfaces.md](interfaces.md#volumes-and-mounts)), which is what `scripts/backup.sh` archives. The media
library, Plex's cache and the transcode directory are never archived.

## How changes reach the host

1. Dependabot (or the maintainer) opens a pull request that changes an image's tag and digest.
2. CI resolves the Compose file, runs the policy check and the smoke test.
3. The pull request is squash-merged (automatically for Dependabot's version updates and the maintainer's own
   pull requests, once every check passes); a version tag makes a signed release.
4. Before deploying, the maintainer reads the release notes, above all for a major version.
5. On the host: back up, `git checkout <tag>`, `docker compose pull && docker compose up -d`
   ([upgrading.md](upgrading.md)).

Nothing on the host updates itself: a version that runs is always a version that's in git. Plex's own in-app
updater doesn't apply to its container; a new Plex version arrives as a new image.

## Repository layout

| Path | What |
| --- | --- |
| `compose.yaml` | The stack |
| `compose.gpu.yaml` | The NVIDIA GPU for Plex, added on the host with `COMPOSE_FILE` |
| `.env.example`, `plex.env.example`, `autoheal.env.example` | Templates for the settings, Plex's claim token and autoheal's optional webhook |
| `scripts/check_compose.py` | The policy check and SBOM generator (standard-library Python) |
| `scripts/backup.sh`, `scripts/restore.sh` | Backup and restore of every service's data, never the media library |
| `scripts/smoke-test.sh` | Starts the stack in isolation, waits for health, and round-trips a backup |
| `tests/` | The checker's tests, with JSON fixtures |
| `docs/` | This documentation |
| `.github/` | CI, release and security workflows, Dependabot, templates |
