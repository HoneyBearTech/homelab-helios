# homelab-helios

[![CI](https://github.com/HoneyBearTech/homelab-helios/actions/workflows/ci.yml/badge.svg)](https://github.com/HoneyBearTech/homelab-helios/actions/workflows/ci.yml)
[![CodeQL](https://github.com/HoneyBearTech/homelab-helios/actions/workflows/codeql.yml/badge.svg)](https://github.com/HoneyBearTech/homelab-helios/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/HoneyBearTech/homelab-helios/badge)](https://scorecard.dev/viewer/?uri=github.com/HoneyBearTech/homelab-helios)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/15291/badge)](https://www.bestpractices.dev/projects/15291)
[![OpenSSF Baseline](https://www.bestpractices.dev/projects/15291/baseline)](https://www.bestpractices.dev/projects/15291)

Docker Compose stack for Helios, a homelab Ubuntu server (24.04, amd64, with an NVIDIA GPU). Version-pinned, self-hosted services, kept as code for easy upgrades and rebuilds.

> [!WARNING]
> Plex's database holds every library, watch history and the server's link to its Plex account, and Plex
> migrates it on many upgrades in a way older versions can't read. Back up the services' data before every
> upgrade ([docs/upgrading.md](docs/upgrading.md)). If you turn on Plex's remote access, Plex is reachable from
> the internet: read [running it securely](#running-it-securely) first.

## Documentation

- [Quick start](docs/quick-start.md): getting the stack running on a fresh Docker host
- [Installing](docs/installing.md): host preparation (including the NVIDIA runtime), where data lives, running it securely, uninstalling
- [Upgrading](docs/upgrading.md): moving to a new release, backup and restore, rolling back
- [Rebuilding](docs/rebuilding.md): a new or wiped host, from a backup
- [Architecture](docs/architecture.md): the services, actors, data flow and how updates reach the host
- [Interfaces](docs/interfaces.md): every setting, port, volume, label and command
- [Verifying releases](docs/verifying-releases.md): checking signatures, checksums, provenance and the SBOM
- [Security requirements](docs/security.md): what the stack protects, what it doesn't, where secrets live
- [Assurance case](docs/assurance-case.md): threat model, trust boundaries, secure design, common weaknesses
- [Dependencies](docs/dependencies.md): how images and tools are chosen, pinned, tracked and patched
- [Roadmap](docs/roadmap.md): the next year, and what homelab-helios will not do
- Project policies: [CONTRIBUTING](CONTRIBUTING.md) · [SECURITY](SECURITY.md) · [GOVERNANCE](GOVERNANCE.md) ·
  [SUPPORT](SUPPORT.md) · [CODE OF CONDUCT](CODE_OF_CONDUCT.md) · [CHANGELOG](CHANGELOG.md)

## What's in the stack

From their upstream images ([architecture](docs/architecture.md), ports in [interfaces](docs/interfaces.md#services-and-ports)):

- **Plex Media Server**: serves the media library to Plex apps, transcoding on the GPU (NVENC/NVDEC)
- **Tautulli**: watches Plex: activity, history, statistics and notifications
- **AURA** (MediUX): browses MediUX artwork sets and applies them to Plex, saving artwork next to the media or
  handing sets to Kometa
- **Kometa**: builds Plex collections and overlays and applies artwork and metadata, once a day; its
  configuration is in `kometa/`, secrets as placeholders, checked in CI and watched upstream ([docs/kometa.md](docs/kometa.md))
- **ImageMaid**: cleans out images Plex no longer uses from Plex's data directory
- **Kometa Quickstart**: a web UI for building Kometa configurations; a tool started on demand, without a login
  ([docs/kometa-quickstart.md](docs/kometa-quickstart.md))
- **autoheal**: restarts any service whose health check fails (Docker on its own only restarts a container that
  exits), reaching Docker only through **socket-proxy**, which lets it list, inspect, restart and stop containers
- **Dozzle agent**: serves the containers' logs to the homelab's Dozzle on another host, which shows every host's
  logs in one web UI

Every service has a health check that autoheal watches, and every image is pinned by tag **and** digest, for
`linux/amd64`. New versions arrive as Dependabot pull requests that CI checks before they're merged.
The maintainer's server follows `main`: a pull agent there applies each merge within a couple of minutes
([upgrading](docs/upgrading.md#following-main)). Nothing updates from a registry tag by itself: what runs is always a
commit in `main`.

## Getting started

On a fresh Docker host:

```sh
git clone https://github.com/HoneyBearTech/homelab-helios.git && cd homelab-helios
cp .env.example .env && chmod 600 .env              # then set TZ, PUID/PGID, MEDIA_PATH and CONFIG_ROOT
CONFIG_ROOT=$(sed -n 's/^CONFIG_ROOT=//p' .env) && mkdir -p "$CONFIG_ROOT"/plex/{config,cache,transcode} \
  "$CONFIG_ROOT"/{tautulli,imagemaid,quickstart}/config \
  "$CONFIG_ROOT"/aura/config/auraassets "$CONFIG_ROOT"/kometa/config/aura
echo 'COMPOSE_FILE=compose.yaml:compose.gpu.yaml' >> .env   # with an NVIDIA GPU
docker compose up -d --wait
```

The host needs the NVIDIA driver, the NVIDIA Container Toolkit 1.18+ and Docker Engine 29.2+ (or Plex loses the GPU
at every `systemctl daemon-reload`), and the Plex account a Plex Pass, for Plex to transcode on the GPU
([installing](docs/installing.md#the-gpu-and-docker-292)). The full steps are in the
[quick start](docs/quick-start.md).

## Usage

```sh
docker compose ps                 # what's running
docker compose logs -f <service>  # one service's log
make check                        # policy check: every image pinned, nothing privileged
scripts/backup.sh                 # back up every service's data (stops each briefly), never the media library
```

Upgrading to a new release, or following `main` the way the maintainer's server does:
[docs/upgrading.md](docs/upgrading.md).

## Configuration

Settings come from `.env` (template [`.env.example`](.env.example)), which holds no secrets.

| Setting | Default in `.env.example` | Meaning |
| --- | --- | --- |
| `TZ` | `Etc/UTC` | Time zone |
| `PUID`, `PGID` | `1000` | User and group Plex, Tautulli and Kometa run as; must be able to read and write the media library |
| `MEDIA_PATH` | `/srv/media` | The media library, mounted read-write into Plex and AURA (never backed up by this stack) |
| `CONFIG_ROOT` | `/srv/config` | Where every app keeps its data: `CONFIG_ROOT/<app>/config` (settings, database, tokens) and the app's other folders beside it, such as Plex's cache and transcode directory (not backed up). Never inside `/var/lib/docker/volumes` ([why](docs/installing.md#where-data-lives)) |
| `KOMETA_TIMES` | `07:30` | When Kometa runs each day (after the nightly backup) |

A new Plex server's one-time claim token goes in a gitignored `plex.env`, never in `.env`
([interfaces](docs/interfaces.md#plexenv)). Ports, volumes and labels: [docs/interfaces.md](docs/interfaces.md).

## Running it securely

- Decide deliberately whether Plex's remote access is on. If it is, Plex is reachable from the internet: use a
  strong password and two-factor authentication on the Plex account that owns the server, share libraries only
  with accounts you know, and keep Plex's "allowed without authentication" networks to the LAN or empty.
- Keep the other web UIs (Tautulli's, AURA's) on your LAN, behind a reverse proxy with access lists, and turn on
  Tautulli's login. Docker-published ports bypass host firewalls such as `ufw`.
- Plex and AURA can write to the media library (AURA saves artwork there; Plex deletes files if you allow media
  deletion). Keep snapshots of it on the storage that holds it; this stack never backs it up.
- The GPU is given to Plex as a device reservation through the NVIDIA runtime, never by running it privileged.
- Secrets (Plex and MediUX tokens, Kometa's API keys, logins) live only in each service's data, never in this repository
  or `.env`. Backups contain them, and Plex's and Tautulli's viewing history: keep them private and off the host.
- The Dozzle agent reads logs through the Docker socket: keep its port (7007) on the LAN. autoheal never gets the
  Docker socket: it goes through a proxy that only lets it list, inspect, restart and stop containers. Its
  optional webhook URL (restart notices, for example to Discord) goes in `autoheal.env` (template
  [`autoheal.env.example`](autoheal.env.example), mode `600`, gitignored).
- Don't run an auto-updater such as Watchtower on these containers; upgrade from this repository instead (a
  release, or `main`).
- Every service drops every Linux capability and runs with `no-new-privileges`, adding back only what its image
  needs. The policy check refuses that being skipped, privileged containers, capabilities beyond Docker's
  defaults, device mappings, host networking and Docker socket mounts unless a service documents why
  ([docs/security.md](docs/security.md#hardening)).

Report vulnerabilities privately: [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE)
