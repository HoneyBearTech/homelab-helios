# Installing

The [quick start](quick-start.md) is the short version of this page.

## Requirements

- Linux with Docker Engine and the Compose v2 plugin (Docker Engine 25 or later and Compose 2.24 or later, for
  the health checks' `start_interval` and GPU device reservations). The reference host is **Ubuntu 24.04 on
  amd64**; every image is chosen to publish `linux/amd64`.
- For hardware transcoding: an **NVIDIA GPU** (passed through to the VM if the host is virtual), the NVIDIA
  driver, the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
  configured for Docker (`sudo nvidia-ctk runtime configure --runtime=docker`, then restart Docker), and a
  **Plex Pass** on the server's Plex account. Without them, Plex still runs and transcodes on the CPU.
- A user in the `docker` group to run `docker compose`. Membership is equivalent to root on the host, so keep
  that group small.
- The media library mounted on the host (local disk or a network share) and readable and writable by
  `PUID`/`PGID` (AURA saves artwork next to the media; Plex deletes files only if you allow it).
- Disk for Plex's data: its metadata and thumbnails grow with the library and can reach tens of gigabytes. Put
  the transcode directory on fast local disk with room for several streams at once, not on the network share.

## Where data lives

| What | Where on the host | In the container |
| --- | --- | --- |
| The media library | `MEDIA_PATH` | `/media` (Plex and AURA) |
| Plex's database, metadata and settings | `PLEX_CONFIG_PATH` | `/config` |
| Plex's cache | `PLEX_CACHE_PATH` | Plex's `Cache` directory under `/config` |
| Plex's transcodes in progress | `PLEX_TRANSCODE_PATH` | `/transcode` |
| Tautulli's database and settings | `TAUTULLI_CONFIG_PATH` | `/config` |
| AURA's settings and tokens | `AURA_CONFIG_PATH` | `/config` |
| Artwork sets AURA hands to Kometa | `KOMETA_CONFIG_PATH`'s `aura` directory | AURA: `/kometa` |
| Kometa's configuration, collections, overlays, assets | `KOMETA_CONFIG_PATH` | `/config` |
| AURA's artwork, read by Kometa | `AURA_CONFIG_PATH`'s `auraassets` directory | Kometa: `/auraassets` |
| ImageMaid's settings | `IMAGEMAID_CONFIG_PATH` | `/config` |
| Kometa Quickstart's database, with the configs and tokens entered in it | `QUICKSTART_CONFIG_PATH` | `/config` |
| Plex's data, cleaned by ImageMaid | `PLEX_CONFIG_PATH`'s `Library/Application Support/Plex Media Server` | ImageMaid: `/plex` |

Every mount is listed in [interfaces.md](interfaces.md#volumes-and-mounts).

## Installing

1. Clone the repository (or download a release's source archive and verify it,
   [verifying-releases.md](verifying-releases.md)).
2. Create `.env` from `.env.example` (mode `600`) and set every value.
3. Create the data directories, then `docker compose up -d`.

**Adopting existing containers.** If the services already run on the host (from Portainer stacks or another
Compose project), point the stack at their existing data instead of starting empty: stop the old containers,
set each path in `.env` to where its data already is, and keep the same published ports and the **same
container path for the media library**: Plex stores every file's path in its database, so a different mount
point makes it see a new library and rescan everything, losing watch state for files it can't match. Keep the
same image family too (Plex's own or LinuxServer.io's), since they lay out `/config` differently. Take a backup
of the old data first.

Running `main` instead of a release is possible but unsupported for anything you depend on.

## Running it securely

- **Decide deliberately about Plex's remote access.** Turning it on makes Plex reachable from the internet
  (directly through a forwarded port, or through plex.tv's relay). Plex requires a Plex account sign-in for
  remote viewers, so use a strong password and two-factor authentication on the server owner's account, and
  share libraries only with accounts you know.
- **Review Plex's "allowed without authentication" networks.** Any address listed there can use the server
  without signing in; keep it to the LAN, or empty.
- **Other web UIs on the LAN only.** Tautulli and AURA shouldn't be published beyond the LAN; Docker-published
  ports bypass host firewalls such as `ufw`, so restrict them at the router or with Docker's own `DOCKER-USER`
  rules, and use a reverse proxy's access lists for names you give them. Turn on Tautulli's login.
- **Kometa Quickstart only while you use it.** It has no login and holds the tokens entered in it: start it on
  demand, stop it after, never forward port 7171 ([quickstart.md](quickstart.md)).
- **Protect the media library.** Plex and AURA mount it read-write: AURA writes artwork into it, and Plex
  deletes files when its "allow media deletion" option is on and someone deletes from a Plex app. Leave that
  option off unless you need it, and keep snapshots on the storage that holds the library.
- **The GPU through the NVIDIA runtime only.** Plex gets the GPU as a device reservation; never run it
  privileged to reach the GPU.
- Keep `.env` at mode `600`; it holds no secrets by design, but it describes your host. `plex.env` holds the
  claim token: mode `600`, emptied once the server is claimed.
- Back up the services' data directories ([upgrading.md](upgrading.md#backing-up)). They hold Plex and MediUX
  tokens and Kometa's API keys.
- Don't add services that mount the Docker socket, run privileged or use the host network without a documented
  reason; the policy check refuses them ([security.md](security.md)).
- Don't run an auto-updater (such as Watchtower) on these containers: it would replace the pinned, reviewed
  versions with whatever a tag points to today.

## Uninstalling

```sh
docker compose down          # stops and removes the containers and the stack's network
```

The data directories, Plex's cache and transcode directory, and the media library are left untouched. Remove
the data directories by hand if you no longer want the services' data. To remove the server from your Plex
account as well, do it in Plex's account settings on plex.tv.
