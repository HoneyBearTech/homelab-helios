# Interfaces

Everything homelab-helios reads, exposes or runs. homelab-helios has no HTTP API of its own; the services' web
UIs and APIs are documented by their projects.

## Settings

### `.env`

Read by `docker compose` from `.env` next to `compose.yaml` (template: [`.env.example`](../.env.example)). A
setting marked required stops `docker compose` with an error naming it when it's missing.

| Setting | Required | Example | Meaning |
| --- | --- | --- | --- |
| `COMPOSE_FILE` | no | `compose.yaml:compose.gpu.yaml` | Read by Docker Compose itself: set it on a host with an NVIDIA GPU so Plex uses it ([GPU](#gpu)). |
| `TZ` | yes | `Etc/UTC` | Time zone (tz database name) for logs and schedules. |
| `PUID`, `PGID` | yes | `1000` | User and group Plex, Tautulli and Kometa run as; must be able to read and write the media library. |
| `MEDIA_PATH` | yes | `/srv/media` | Host path of the media library, mounted read-write into Plex and AURA. Never backed up by this stack. |
| `CONFIG_ROOT` | yes | `/srv/config` | Host directory every app keeps its data in: `CONFIG_ROOT/<app>/config` (`<app>` is the service's name) at the app's data path, and the app's other folders beside it as `CONFIG_ROOT/<app>/<purpose>` (Plex's `cache` and `transcode`, never backed up). Never inside `/var/lib/docker/volumes`: a volume prune deletes data kept there ([installing.md](installing.md#where-data-lives)). |
| `KOMETA_TIMES` | no | `02:00` | When Kometa runs each day (`HH:MM`, comma-separated). |
| `IMAGEMAID_SCHEDULE` | yes | `22:00\|weekly(sunday)` | When ImageMaid runs, in its own schedule syntax. |
| `UMASK` | no | `002` | File-creation mask for Plex and Tautulli. |

### `autoheal.env`

Read by the `autoheal` service (template: [`autoheal.env.example`](../autoheal.env.example));
optional, mode `600`, gitignored.

| Setting | Meaning |
| --- | --- |
| `WEBHOOK_URL` | Where autoheal posts a notice each time it restarts a container (a secret). A Discord channel webhook works as is; empty or missing = log only |

### `backup.env`

Read by `scripts/scheduled-backup.sh` (template: [`backup.env.example`](../backup.env.example)); optional, mode
`600`, gitignored. Read as data, never run: only these keys, one `KEY=value` per line; anything else is an error.

| Setting | Default | Meaning |
| --- | --- | --- |
| `BACKUP_DIR` | `backups` | Where backups are written (relative to the checkout, or absolute). |
| `BACKUP_KEEP` | `3` | How many backups are kept in `BACKUP_DIR`; older ones are deleted. |
| `BACKUP_REMOTE` | empty | rsync destination each backup is copied to, such as `backup-host:/volume1/helios-backups` (an SSH alias); empty = no copy. |
| `BACKUP_REMOTE_KEEP` | `14` | How many backups are kept at `BACKUP_REMOTE`; older ones are deleted. |
| `BACKUP_PING_URL` | empty | An Uptime Kuma push URL (a secret), told `up` after each good run and `down` after a failed one. |

Only directories named like a backup (`<date>-<time>`) are ever deleted, here or at the remote.

### `plex.env`

Plex's one-time claim token (`PLEX_CLAIM`, from [plex.tv/claim](https://www.plex.tv/claim/), valid for a few
minutes) links a new server to a Plex account on its first start. It's a secret, so it goes in the gitignored
`plex.env` (mode `600`, optional, template [`plex.env.example`](../plex.env.example)), and is emptied once the
server is claimed. An adopted server is already claimed and doesn't need it.

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
| Kometa Quickstart | `kometateam/quickstart` (release tags) | 7171 → 7171 | Web UI, no login; only while started on demand (profile `tools`; LAN only, [quickstart.md](kometa-quickstart.md)) |
| autoheal | `willfarrell/autoheal` | none | Restarts services whose health check fails |
| socket-proxy | `lscr.io/linuxserver/socket-proxy` | none (internal network `docker-proxy`) | Filtered Docker API for autoheal |
| Dozzle agent | `amir20/dozzle` (`command: agent`) | 7007 → 7007 | Agent for the homelab's Dozzle on another host, no web UI of its own (LAN only) |

Plex runs on the stack's own network, not the host's, so only 32400 is published. Its local discovery ports (GDM
on UDP 32410–32414, DLNA on UDP 1900 and TCP 32469) aren't: players find the server through plex.tv instead.
Plex keeps the client's address (Docker forwards published ports without rewriting it), so its LAN networks and
"allowed without authentication" settings still work. LinuxServer.io's `VERSION` setting is fixed to `docker`, so
Plex runs the version in the pinned image and never downloads another at start. Exact versions and digests are in [`compose.yaml`](../compose.yaml).

## GPU

Plex gets the host's NVIDIA GPU as a Compose device reservation (`driver: nvidia`, `capabilities: [gpu]`, with
`NVIDIA_DRIVER_CAPABILITIES` including `video` for NVENC/NVDEC), which needs the NVIDIA Container Toolkit on the
host. Hardware transcoding in Plex also needs a Plex Pass. The reservation lives in
[`compose.gpu.yaml`](../compose.gpu.yaml), so the stack also starts on a machine without a GPU (such as CI);
the host adds it with `COMPOSE_FILE=compose.yaml:compose.gpu.yaml` in `.env`.

## Volumes and mounts

Every mount is a host directory: the stack declares no named Docker volumes, and no service keeps data in one.

| Container path | Host source | Service |
| --- | --- | --- |
| `/media` | `MEDIA_PATH` | Plex: the media library (read-write; never backed up) |
| `/config` | `CONFIG_ROOT/plex/config` | Plex: database, metadata, settings |
| Plex's `Cache` directory under `/config` | `CONFIG_ROOT/plex/cache` | Plex: cache (not backed up) |
| `/transcode` | `CONFIG_ROOT/plex/transcode` | Plex: transcodes in progress (not backed up) |
| `/config` | `CONFIG_ROOT/tautulli/config` | Tautulli: database, settings, Plex token |
| `/config` | `CONFIG_ROOT/aura/config` | AURA: settings, Plex and MediUX tokens |
| `/kometa` | `CONFIG_ROOT/kometa/config/aura` | AURA: artwork sets for Kometa (backed up with Kometa's data) |
| `/config` | `CONFIG_ROOT/kometa/config` | Kometa: its `.env` (secrets), overlays, assets, cache, logs |
| `/config/config.yml` and `/config/<name>.yml` for each collection file | `kometa/` in the checkout, read-only | Kometa: its configuration, placeholders only (not backed up: it's in git) |
| `/auraassets` | `CONFIG_ROOT/aura/config/auraassets` | Kometa: AURA's artwork (backed up with AURA's data) |
| `/config` | `CONFIG_ROOT/imagemaid/config` | ImageMaid: settings |
| `/config` | `CONFIG_ROOT/quickstart/config` | Quickstart: its SQLite database (configs, with the Plex token and API keys entered in it), logs, caches |
| `/plex` | `CONFIG_ROOT/plex/config/Library/Application Support/Plex Media Server` | ImageMaid: Plex's data, to clean (backed up with Plex's data) |
| `/plex/Cache` | `CONFIG_ROOT/plex/cache` | ImageMaid: Plex's cache, for its PhotoTranscoder cleanup (not backed up) |
| `/media` | `MEDIA_PATH` | AURA: saves artwork next to the media (read-write; never backed up) |
| `/var/run/docker.sock` (read-only) | the Docker socket | socket-proxy and the Dozzle agent only (allowed exceptions, see below; not backed up) |

`socket-proxy` and `autoheal` share the internal network `docker-proxy`, which has no route out and nothing
published; autoheal also joins the default network, to reach its webhook.

## Labels

| Label | Meaning |
| --- | --- |
| `org.honeybeartech.helios.allow.<rule>` | Lets one service break one policy rule; the value is the reason, and must not be empty. Rules: `image`, `digest`, `latest`, `build`, `privileged`, `no-new-privileges`, `cap-drop`, `cap-add`, `host-network`, `host-pid`, `docker-socket`, `devices`, `healthcheck` ([security.md](security.md#policy)). In use: `socket-proxy` and `dozzle-agent` (`docker-socket`), and `autoheal` (`latest`, since its image publishes no current version tags), as on the sibling stacks. |
| `org.honeybeartech.helios.backup.skip` | Container paths (comma-separated, exact) that `scripts/backup.sh` never archives and `scripts/restore.sh` refuses to write, even if a backup lists them. In use: `/media`, the cache and `/transcode` for Plex; `/media` and `/kometa` for AURA; `/auraassets` for Kometa; `/plex` and `/plex/Cache` for ImageMaid (each of those is either never backed up or already backed up with the service that owns it). |
| `org.honeybeartech.helios.backup.exclude` | Paths inside a service's data mounts (comma-separated, exact container paths) that `scripts/backup.sh` leaves out of the mount's archive and `scripts/restore.sh` leaves in place: data the services re-create, too large to copy every night. A path that isn't inside one of the service's data mounts, or contains `..` or a pattern character (`*?[\`), makes both fail before anything stops. In use: Plex's `Metadata` (artwork) and `Media` (preview thumbnails) under `/config/Library/Application Support/Plex Media Server`; `/config/assets` for Kometa. |
| `autoheal` | `"true"` on every service autoheal may restart when its health check fails (every service, socket-proxy included). autoheal restarts only containers with this label, so other containers on the host are left alone. |
| `com.centurylinklabs.watchtower.enable` | `"false"` on every service, so an auto-updater such as Watchtower running on the same host never replaces a pinned version. |

## Commands

| Command | Does |
| --- | --- |
| `docker compose up -d` / `down` / `ps` / `logs <service>` | Runs and inspects the stack (without the tools) |
| `docker compose --profile tools up -d quickstart` / `stop quickstart` | Starts and stops Kometa Quickstart, the one tool ([quickstart.md](kometa-quickstart.md)) |
| `make check` | `docker compose --profile tools config --format json \| python scripts/check_compose.py`: the policy check, tools included |
| `python scripts/check_compose.py [FILE] [--sbom OUT]` | Checks a resolved Compose config (from `FILE` or stdin); `--sbom` also writes a CycloneDX 1.6 SBOM of the images. Exit 0 = no violations, 1 = violations (one line each), 2 = unreadable input |
| `make test`, `make lint` | The checker's tests and the linters |
| `scripts/backup.sh [DIR]` | Archives every service's data mounts (every read-write volume or bind mount except the Docker socket, anonymous volumes and the paths in the service's `backup.skip` label: the media library, Plex's cache and transcode directory; a mount inside another mount, such as Plex's cache inside its `/config`, and the paths in the service's `backup.exclude` label are left out of the outer archive), `.env` and any `<service>.env` into `DIR` (default `backups/<date>-<time>`, gitignored) with a `MANIFEST`, `NETWORKS` (the address range of each network the stack uses but doesn't create; none today, so only its header), `VERSION` (the checkout's `git describe`) and `SHA256SUMS`, all mode `600`. Each service is stopped only while its own data is copied and started again (with any service Compose stopped along with it) before the copy is compressed (with `pigz` when it's installed, else `gzip`). A tool that has never been started (Quickstart) has no data yet and is skipped. Holds the pull agent's deploy lock from the start (see below). If stopping a service fails while its container is still on its way down (a process stuck writing to a network share can outlast Docker's stop), it waits up to `BACKUP_STOP_WAIT` seconds (default 120) for the container to exit and carries on; if it still runs then, the backup fails, and the services are started again only after a second wait. Fails, naming them, if any service that was running when it began isn't running again at the end. Exit 0 = backup complete |
| `scripts/scheduled-backup.sh` | Runs `scripts/backup.sh` into `BACKUP_DIR/<date>-<time>`, copies it to `BACKUP_REMOTE` with rsync (`SHA256SUMS` last), deletes all but the newest `BACKUP_REMOTE_KEEP` there and `BACKUP_KEEP` here, and reports to `BACKUP_PING_URL` ([`backup.env`](#backupenv)). Run nightly by the systemd user units in `deploy/systemd/` |
| `scripts/restore.sh [--yes] DIR [SERVICE...]` | Verifies `DIR/SHA256SUMS`, checks the `MANIFEST`, asks for confirmation (unless `--yes`), stops the services, replaces the contents of each listed mount with its archive, and starts what was running. Each archive goes to what `compose.yaml` mounts at its container path now, whatever host path the `MANIFEST` names: a container created from an older `compose.yaml` or `.env` is recreated first, and a missing directory is created (so a backup taken before `CONFIG_ROOT` restores into the new directories). Writes only mounts the service still has read-write; never the Docker socket, a path in the service's `backup.skip` label, another mount inside the one it restores, or a path in its `backup.exclude` label. Fails before anything stops if a `backup.exclude` label is invalid. Holds the pull agent's deploy lock from the start |
| `make smoke` | `scripts/smoke-test.sh`: starts every service under a separate Compose project with throwaway directories (owned by `PUID:PGID`, mode 0755, as on a host), no GPU and no published ports, waits until all are healthy, round-trips a backup and restore over every data mount (one app's config directory removed and its container recreated from other settings first, to check the restore recreates the directory where `compose.yaml` says), checks the backup's `NETWORKS` and `VERSION`, checks that excluded mounts and left-out paths were neither archived nor overwritten, runs the scheduled backup against a stand-in backup server and checks the copy and the pruning, makes a test container unhealthy and checks that autoheal restarts it, then removes what it created. Exit 0 = all healthy and restored (or no `compose.yaml` yet) |

`scripts/backup.sh` and `scripts/restore.sh` take the lock the server's pull agent holds while it deploys (`flock` on `homelab-pull/helios/lock` under `HOMELAB_PULL_STATE_DIR`, else `XDG_STATE_HOME`, else `~/.local/state`), wait up to 30 minutes for a deploy in progress (then exit 1 without stopping anything) and keep it until they exit, so no deploy overlaps them. Where that directory doesn't exist (no agent), they don't lock.

## Outbound connections

From the host: the image registries (Docker Hub, GitHub Container Registry, LinuxServer.io's) on
`docker compose pull`; the media library's storage. From the services: Plex talks to plex.tv for sign-in,
remote access and metadata (posters, descriptions) and to its metadata providers; Tautulli talks to Plex and,
for notifications, to whatever services you configure; AURA talks to MediUX for artwork and to Plex; Kometa
talks to Plex, TMDb and whatever other sources its `config.yml` names; ImageMaid talks to Plex; Kometa Quickstart,
while it runs, talks to GitHub (Kometa's schemas and defaults), Plex and the services whose credentials it checks.
The scheduled backup talks to `BACKUP_REMOTE` (rsync, usually over SSH) and `BACKUP_PING_URL`, if they are set.

## Release files

Each GitHub Release has `homelab-helios-<version>.tar.gz` (source, with `LICENSE`),
`homelab-helios-<version>.cdx.json` (CycloneDX SBOM of the pinned images), `SHA256SUMS` and its Sigstore
bundle, and SLSA provenance ([verifying-releases.md](verifying-releases.md)).
