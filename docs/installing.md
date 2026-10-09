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
| Kometa's secrets (`.env`), overlays, assets, cache, logs | `KOMETA_CONFIG_PATH` | `/config` |
| Kometa's configuration and collection files (placeholders only) | `kometa/` in the checkout, read-only | `/config/config.yml`, `/config/<name>.yml` |
| AURA's artwork, read by Kometa | `AURA_CONFIG_PATH`'s `auraassets` directory | Kometa: `/auraassets` |
| ImageMaid's settings | `IMAGEMAID_CONFIG_PATH` | `/config` |
| Kometa Quickstart's database, with the configs and tokens entered in it | `QUICKSTART_CONFIG_PATH` | `/config` |
| Plex's data, cleaned by ImageMaid | `PLEX_CONFIG_PATH`'s `Library/Application Support/Plex Media Server` | ImageMaid: `/plex` |

Every mount is listed in [interfaces.md](interfaces.md#volumes-and-mounts).

## Installing

1. Clone the repository (or download a release's source archive and verify it,
   [verifying-releases.md](verifying-releases.md)).
2. Create `.env` from `.env.example` (mode `600`) and set every value.
3. Create the data directories. Create Kometa's secrets file from `kometa.env.example`, owned by `PUID` and
   readable only by it, and fill in every value:
   `sudo install -m 600 -o <PUID> -g <PGID> kometa.env.example <KOMETA_CONFIG_PATH>/.env` (the values from
   `.env`). Kometa reads it itself, so the values stay out of the container's environment. Its configuration,
   `kometa/`, holds only `<<UPPER_SNAKE>>` placeholders, which Kometa fills from these `KOMETA_*` values.
4. `docker compose up -d`, then check Kometa's configuration with the real values:
   `docker compose run --rm kometa --validate --validate-level full` should end with `Result: PASSED`.

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
- Back up the services' data directories ([upgrading.md](upgrading.md#backing-up)), and schedule a nightly copy
  off the host ([Scheduled backups](#scheduled-backups)). They hold Plex and MediUX tokens and Kometa's API keys.
- Don't add services that mount the Docker socket, run privileged or use the host network without a documented
  reason; the policy check refuses them ([security.md](security.md)).
- Don't run an auto-updater (such as Watchtower) on these containers: it would replace the pinned, reviewed
  versions with whatever a tag points to today.

## Scheduled backups

`scripts/scheduled-backup.sh` takes a backup (`scripts/backup.sh`), copies it to another machine with rsync, keeps
only the newest few in both places and reports to an Uptime Kuma push monitor. A systemd timer runs it nightly.
Every setting is in the optional `backup.env` ([interfaces.md](interfaces.md#backupenv)). The backups hold every
login and token: copy them only to a machine you trust as much as this one.

A nightly backup leaves out Plex's artwork and preview thumbnails and Kometa's downloaded assets (their
`backup.exclude` labels, [interfaces.md](interfaces.md#labels)), so it is the databases, settings and Kometa's
overlay originals rather than the whole of Plex's data: Plex is stopped for a few minutes, not for hours. A
restore leaves those paths alone, and on a new host Plex, Kometa and AURA re-create them
([rebuilding.md](rebuilding.md#what-the-backup-doesnt-bring-back)).

1. **On the backup server**, create a folder for the backups and a user that can write only there and use rsync
   over SSH (on a Synology: a shared folder, a non-admin user with read/write on that folder only, rsync allowed
   under Application Privileges, SSH on, the rsync service on under File Services, and the user home service on so
   the user can have an `authorized_keys`). Whoever controls this host can delete or overwrite what it copied
   there, so keep older versions where the backup user can't reach them: snapshots of the folder, or a versioned
   copy of it made on the server after the nightly backup (on a Synology without Btrfs, a Hyper Backup task with
   rotation, into a folder the backup user has no access to). A recycle bin isn't enough: Synology's doesn't keep
   files deleted over rsync.
2. **On this host**, as the user who runs the stack, install rsync and curl (and pigz, which compresses the
   archives on every core instead of one), and create a key used only for the backups, with an alias for it in
   `~/.ssh/config`:

   ```sh
   sudo apt install -y rsync curl pigz
   ssh-keygen -t ed25519 -N '' -f ~/.ssh/homelab-helios-backup
   ```

   ```text
   Host backup-host
     HostName <the backup server's address>
     User <the backup user>
     IdentityFile ~/.ssh/homelab-helios-backup
     IdentitiesOnly yes
   ```

   Add the public key to the backup user's `~/.ssh/authorized_keys` on the server, prefixed with
   `restrict,from="<this host's address>"` (no shell or forwarding, and only from this host), then check that
   `rsync --list-only backup-host:/volume1/<folder>/` works without a password prompt.
3. **Settings**: `cp backup.env.example backup.env && chmod 600 backup.env`, then set
   `BACKUP_REMOTE=backup-host:/volume1/<folder>` and, optionally, the retention and `BACKUP_PING_URL`. For the
   ping, add a monitor of type **Push** in Uptime Kuma with a heartbeat interval of 25 hours, and copy its URL.
4. **Try it**: `scripts/scheduled-backup.sh`. Each service stops only while its own data is copied, and the
   archives are compressed after it has started again.
5. **Schedule it**, with the systemd user units in [`deploy/systemd/`](../deploy/systemd/) (they expect the
   checkout at `~/homelab-helios`; edit both paths in the `.service` file if it's elsewhere). Lingering lets the
   timer run while you're logged out:

   ```sh
   mkdir -p ~/.config/systemd/user
   cp deploy/systemd/homelab-helios-backup.* ~/.config/systemd/user/
   sudo loginctl enable-linger "$USER"
   systemctl --user daemon-reload
   systemctl --user enable --now homelab-helios-backup.timer
   systemctl --user list-timers homelab-helios-backup.timer   # next run: 01:00, plus up to 5 minutes
   journalctl --user -u homelab-helios-backup                 # what the last runs did
   ```

   01:00 leaves the backup time to finish before Kometa's run at 02:00 (`KOMETA_TIMES`); if you move either, keep
   them apart, since the backup stops Kometa while it copies Kometa's data.

Restore a copy from the backup server as [rebuilding.md](rebuilding.md) describes; `scripts/restore.sh` verifies
its `SHA256SUMS` first, and a copy that was cut off has none yet, so it is refused.

## Uninstalling

```sh
docker compose down          # stops and removes the containers and the stack's network
```

The data directories, Plex's cache and transcode directory, and the media library are left untouched. Remove
the data directories by hand if you no longer want the services' data. To remove the server from your Plex
account as well, do it in Plex's account settings on plex.tv.
