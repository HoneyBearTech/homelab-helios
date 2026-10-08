# Interfaces

Everything homelab-helios reads, exposes or runs. homelab-helios has no HTTP API of its own; the services' web
UIs and APIs are documented by their projects.

> **Planned:** `compose.yaml` isn't in the repository yet. The settings, services, ports and mounts below are the
> expected ones (the upstream defaults); they are confirmed or corrected when the stack is added. The scripts and commands already exist.

## Settings

### `.env`

Read by `docker compose` from `.env` next to `compose.yaml` (template: [`.env.example`](../.env.example)). A
setting marked required stops `docker compose` with an error naming it when it's missing.

| Setting | Required | Example | Meaning |
| --- | --- | --- | --- |
| `TZ` | yes | `Etc/UTC` | Time zone (tz database name) for logs and schedules. |
| `PUID`, `PGID` | yes | `1000` | User and group Plex, Tautulli and Kometa run as; must be able to read and write the media library. |
| `MEDIA_PATH` | yes | `/srv/media` | Host path of the media library, mounted read-write into Plex and AURA. Never backed up by this stack. |
| `PLEX_CONFIG_PATH` | yes | `/srv/appdata/plex` | Plex's database, metadata and settings. |
| `PLEX_CACHE_PATH` | yes | `/srv/plex-cache` | Plex's cache (disposable, not backed up). |
| `PLEX_TRANSCODE_PATH` | yes | `/srv/plex-transcode` | Scratch space for transcodes in progress (not backed up). |
| `TAUTULLI_CONFIG_PATH` | yes | `/srv/appdata/tautulli` | Tautulli's database and settings. |
| `AURA_CONFIG_PATH` | yes | `/srv/appdata/aura` | AURA's settings, including its Plex and MediUX tokens. |
| `KOMETA_CONFIG_PATH` | yes | `/srv/appdata/kometa` | Kometa's `config.yml` (Plex token, API keys), collection and overlay files, assets, logs. AURA writes artwork sets into its `aura` directory. |
| `KOMETA_TIMES` | no | `02:00` | When Kometa runs each day (`HH:MM`, comma-separated). |
| `IMAGEMAID_CONFIG_PATH` | yes | `/srv/appdata/imagemaid` | ImageMaid's settings, with its Plex token. |

### `autoheal.env`

**Planned.** Read by the `autoheal` service (template: [`autoheal.env.example`](../autoheal.env.example));
optional, mode `600`, gitignored.

| Setting | Meaning |
| --- | --- |
| `WEBHOOK_URL` | Where autoheal posts a notice each time it restarts a container (a secret). A Discord channel webhook works as is; empty or missing = log only |

### `plex.env`

**Planned.** Plex's one-time claim token (`PLEX_CLAIM`, from [plex.tv/claim](https://www.plex.tv/claim/), valid
for a few minutes) links a new server to a Plex account on its first start. It's a secret, so it goes in a
gitignored `plex.env` (mode `600`) read through `env_file`, with a committed `plex.env.example`, and can be
emptied once the server is claimed. An adopted server is already claimed and doesn't need it.

No other secret is a setting. If a service ever needs one in its environment, it gets its own gitignored
`<service>.env` (mode `600`) with a committed `<service>.env.example`, listed here.

## Services and ports

| Service | Image | Host port → container | What |
| --- | --- | --- | --- |
| Plex | `lscr.io/linuxserver/plex` | 32400 → 32400 | Plex's API and web app; what Plex apps connect to, and what remote access exposes if it's on |
| Tautulli | `lscr.io/linuxserver/tautulli` | 8181 → 8181 | Web UI and API (LAN only) |
| AURA | `ghcr.io/mediux-team/aura` | 3000 → 3000, 8888 → 8888 | Web UI and its second port (LAN only) |
| Kometa | `kometateam/kometa` (release tags) | none | Runs on its schedule |
| ImageMaid | `kometateam/imagemaid` (release tags) | none | Runs on its schedule |
| autoheal | `willfarrell/autoheal` | none | Restarts services whose health check fails |
| socket-proxy | `lscr.io/linuxserver/socket-proxy` | none (internal network `docker-proxy`) | Filtered Docker API for autoheal |

Plex runs on the stack's own network, not the host's, so only 32400 is published. Its local discovery ports (GDM
on UDP 32410–32414, DLNA on UDP 1900 and TCP 32469) aren't: players find the server through plex.tv instead.
Plex keeps the client's address (Docker forwards published ports without rewriting it), so its LAN networks and
"allowed without authentication" settings still work. LinuxServer.io's `VERSION` setting is fixed to `docker`, so
Plex runs the version in the pinned image and never downloads another at start. Exact versions and digests will be in [`compose.yaml`](../compose.yaml).

## GPU

Plex gets the host's NVIDIA GPU as a Compose device reservation (`driver: nvidia`, `capabilities: [gpu]`, with
`NVIDIA_DRIVER_CAPABILITIES` including `video` for NVENC/NVDEC), which needs the NVIDIA Container Toolkit on the
host. Hardware transcoding in Plex also needs a Plex Pass. **Planned:** the reservation lives in a separate
override file, so the stack also starts on a machine without a GPU (such as CI).

## Volumes and mounts

| Container path | Host source | Service |
| --- | --- | --- |
| `/media` | `MEDIA_PATH` | Plex: the media library (read-write; never backed up) |
| `/config` | `PLEX_CONFIG_PATH` | Plex: database, metadata, settings |
| Plex's `Cache` directory under `/config` | `PLEX_CACHE_PATH` | Plex: cache (not backed up) |
| `/transcode` | `PLEX_TRANSCODE_PATH` | Plex: transcodes in progress (not backed up) |
| `/config` | `TAUTULLI_CONFIG_PATH` | Tautulli: database, settings, Plex token |
| `/config` | `AURA_CONFIG_PATH` | AURA: settings, Plex and MediUX tokens |
| `/kometa` | `KOMETA_CONFIG_PATH/aura` | AURA: artwork sets for Kometa (backed up with Kometa's data) |
| `/config` | `KOMETA_CONFIG_PATH` | Kometa: `config.yml`, collections, overlays, assets, logs |
| `/auraassets` | `AURA_CONFIG_PATH/auraassets` | Kometa: AURA's artwork (backed up with AURA's data) |
| `/config` | `IMAGEMAID_CONFIG_PATH` | ImageMaid: settings |
| `/plex` | `PLEX_CONFIG_PATH/Library/Application Support/Plex Media Server` | ImageMaid: Plex's data, to clean (backed up with Plex's data) |
| `/plex/Cache` | `PLEX_CACHE_PATH` | ImageMaid: Plex's cache, for its PhotoTranscoder cleanup (not backed up) |
| `/media` | `MEDIA_PATH` | AURA: saves artwork next to the media (read-write; never backed up) |
| `/var/run/docker.sock` (read-only) | the Docker socket | socket-proxy only (an allowed exception, see below) |

`socket-proxy` and `autoheal` share the internal network `docker-proxy`, which has no route out and nothing
published; autoheal also joins the default network, to reach its webhook.

## Labels

| Label | Meaning |
| --- | --- |
| `org.honeybeartech.helios.allow.<rule>` | Lets one service break one policy rule; the value is the reason, and must not be empty. Rules: `image`, `digest`, `latest`, `build`, `privileged`, `cap-add`, `host-network`, `host-pid`, `docker-socket`, `healthcheck` ([security.md](security.md#policy)). Planned: `socket-proxy` (`docker-socket`), and `autoheal` (`latest`) while its image publishes no version tags, as on the sibling stacks. |
| `org.honeybeartech.helios.backup.skip` | Container paths (comma-separated, exact) that `scripts/backup.sh` never archives and `scripts/restore.sh` refuses to write, even if a backup lists them. Planned: `/media`, the cache and `/transcode` for Plex; `/media` and `/kometa` for AURA; `/auraassets` for Kometa; `/plex` and `/plex/Cache` for ImageMaid (each of those is either never backed up or already backed up with the service that owns it). |
| `autoheal` | `"true"` on every service autoheal may restart when its health check fails (every service, socket-proxy included). autoheal restarts only containers with this label, so other containers on the host are left alone. |
| `com.centurylinklabs.watchtower.enable` | `"false"` on every service, so an auto-updater such as Watchtower running on the same host never replaces a pinned version. |

## Commands

| Command | Does |
| --- | --- |
| `docker compose up -d` / `down` / `ps` / `logs <service>` | Runs and inspects the stack |
| `make check` | `docker compose config --format json \| python scripts/check_compose.py`: the policy check |
| `python scripts/check_compose.py [FILE] [--sbom OUT]` | Checks a resolved Compose config (from `FILE` or stdin); `--sbom` also writes a CycloneDX 1.6 SBOM of the images. Exit 0 = no violations, 1 = violations (one line each), 2 = unreadable input |
| `make test`, `make lint` | The checker's tests and the linters |
| `scripts/backup.sh [DIR]` | Stops the stack, archives every service's data mounts (every read-write volume or bind mount except the Docker socket, anonymous volumes and the paths in the service's `backup.skip` label: the media library, Plex's cache and transcode directory), `.env` and any `<service>.env` into `DIR` (default `backups/<date>-<time>`, gitignored) with a `MANIFEST` and `SHA256SUMS`, all mode `600`, then starts what was running |
| `scripts/restore.sh [--yes] DIR [SERVICE...]` | Verifies `DIR/SHA256SUMS`, checks the `MANIFEST`, asks for confirmation (unless `--yes`), stops the services, replaces the contents of each listed mount with its archive, and starts what was running. Writes only mounts the service still has read-write; never the Docker socket or a path in the service's `backup.skip` label |
| `make smoke` | `scripts/smoke-test.sh`: starts every service under a separate Compose project with throwaway directories, no GPU and no published ports, waits until all are healthy, round-trips a backup and restore over every data mount, checks that excluded mounts were neither archived nor overwritten, then removes what it created. Exit 0 = all healthy and restored (or no `compose.yaml` yet) |

## Outbound connections

From the host: the image registries (Docker Hub, GitHub Container Registry, LinuxServer.io's) on
`docker compose pull`; the media library's storage. From the services: Plex talks to plex.tv for sign-in,
remote access and metadata (posters, descriptions) and to its metadata providers; Tautulli talks to Plex and,
for notifications, to whatever services you configure; AURA talks to MediUX for artwork and to Plex; Kometa
talks to Plex, TMDb and whatever other sources its `config.yml` names; ImageMaid talks to Plex.

## Release files

Each GitHub Release will have `homelab-helios-<version>.tar.gz` (source, with `LICENSE`),
`homelab-helios-<version>.cdx.json` (CycloneDX SBOM of the pinned images), `SHA256SUMS` and its Sigstore
bundle, and SLSA provenance ([verifying-releases.md](verifying-releases.md)).
