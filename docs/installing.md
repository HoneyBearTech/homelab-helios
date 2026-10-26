# Installing

The [quick start](quick-start.md) is the short version of this page.

## Requirements

- Linux with Docker Engine and the Compose v2 plugin (Docker Engine 25 or later and Compose 2.24 or later, for
  the health checks' `start_interval`; **Docker Engine 29.2 or later on a host with a GPU**, see
  [below](#the-gpu-and-docker-292)). The reference host is **Ubuntu 24.04 on amd64**; every image is chosen to
  publish `linux/amd64`.
- For hardware transcoding: an **NVIDIA GPU** (passed through to the VM if the host is virtual), the NVIDIA
  driver, the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
  1.18 or later configured for Docker (`sudo nvidia-ctk runtime configure --runtime=docker`, then restart Docker),
  and a **Plex Pass** on the server's Plex account. Without them, Plex still runs and transcodes on the CPU. An
  **Intel GPU** (Arc, or integrated) on the kernel's i915 or xe driver works too, with `compose.intel.yaml`: it
  needs no toolkit, only the GPU's firmware (Ubuntu's `linux-firmware`) and the Plex Pass.
- A user in the `docker` group to run `docker compose`. Membership is equivalent to root on the host, so keep
  that group small.
- The media library mounted on the host (local disk or a network share) and readable and writable by
  `PUID`/`PGID` (AURA saves artwork next to the media; Plex deletes files only if you allow it).
- Disk for Plex's data: its metadata and thumbnails grow with the library and can reach tens of gigabytes. Keep
  `CONFIG_ROOT` on local disk, not on the network share, and give Plex's transcode directory
  (`CONFIG_ROOT/plex/transcode`) fast disk with room for several streams at once (mount another disk there if
  `CONFIG_ROOT` isn't on one).
- `age` if the backups are copied off the host encrypted ([Scheduled backups](#scheduled-backups)).

### The GPU and Docker 29.2

From Docker Engine 29.2, Docker serves the GPU reservation in [`compose.gpu.yaml`](../compose.gpu.yaml)
(`driver: nvidia`) through CDI, the Container Device Interface, whenever the NVIDIA Container Toolkit's
`nvidia-cdi-hook` and a CDI spec for the GPU are installed. Toolkit 1.18 and later ship both, and its
`nvidia-cdi-refresh` keeps the spec current at boot and after every driver install or upgrade
(`nvidia-ctk cdi list` shows `nvidia.com/gpu=all`).

An older Engine passes the GPU through the NVIDIA runtime hook instead, and with Docker's systemd cgroup driver (the
default on cgroup v2) the container then **loses the GPU at every `systemctl daemon-reload`**, which apt and
unattended-upgrades run. Plex falls back to transcoding on the CPU without an error anyone sees, and `nvidia-smi` in
the container fails with "Failed to initialize NVML: Unknown Error"
([NVIDIA container-toolkit issue #48](https://github.com/NVIDIA/nvidia-container-toolkit/issues/48)); only
restarting the container brings the GPU back, until the next reload. The compose files are the same either way:
upgrading Docker is the fix (it restarts every container on the host).

To check a GPU host, reload systemd and ask Plex for the GPU:

```sh
docker version --format '{{.Server.Version}}'   # 29.2 or later
sudo systemctl daemon-reload
docker exec plex nvidia-smi -L                  # still lists the GPU
```

### The GPU at boot

A host whose GPU can change between boots, such as a virtual machine that fails over to another hypervisor with
another card passed through (an NVIDIA card on one, an Intel one on the other), can let Plex follow it.
`scripts/select-gpu.sh` points `compose.host-gpu.yaml`, a gitignored symlink in the checkout, at the override for
the GPU the host has: `compose.gpu.yaml` for an NVIDIA GPU on the `nvidia` driver, `compose.intel.yaml` for an Intel
GPU on `i915` or `xe` with a render node, `compose.cpu.yaml` (no change: CPU transcoding) for neither. When the link
changes, it recreates Plex with the new override (`docker compose up --detach --no-deps --wait plex`), taking the
pull agent's lock first. A systemd user unit runs it at every boot. A GPU passed through to another VM on the host,
or one whose driver didn't load, doesn't count; the script says so in its output.

An [Argus](https://github.com/HoneyBearTech/Argus) agent beside the stack (its `agent/compose.yml` and `.env` in
`~/argus-agent`, or wherever `GPU_ARGUS_AGENT_DIR` says) follows the GPU too: its `gpu` Compose profile runs an NVIDIA
GPU exporter, which can't start without an NVIDIA GPU, and its `intel-gpu` profile an Intel GPU exporter
(`intel_gpu_top`). The script keeps the profile of the GPU it chose for Plex in the `COMPOSE_PROFILES` line of the
agent's `.env` and takes the other out: `gpu` with an NVIDIA GPU on the `nvidia` driver, `intel-gpu` with an Intel
GPU, neither without a GPU Plex can use. When that changes it removes the exporter of the profile that went (`docker
compose rm --stop --force`: `up --remove-orphans` leaves a service whose profile was dropped running), starts the one
of the profile that came (`docker compose up --detach --wait`) and rewrites the line. An agent whose compose file has
no `intel-gpu` profile yet starts nothing for it (Compose ignores a profile no service has); once it has one, the
Intel exporter starts the next time the agent is brought up (`docker compose up -d` in its folder) or the script
switches GPUs. The agent's other containers aren't touched, and the line changes only once the containers have, so a
run that failed is tried again by the next. While the NVIDIA exporter is gone the Argus server can't scrape it; the
metric below tells Argus not to expect it then. Without an agent's `.env` there nothing happens;
`GPU_ARGUS_AGENT_DIR=` (empty) leaves an agent alone.

Every run also tells Argus which GPU it chose, whether or not anything changed: one series,
`homelab_gpu_selected{vendor="nvidia"}`, `{vendor="intel"}` or `{vendor="none"}` with the value 1, in
`homelab-helios-gpu.prom` in the pull agent's metrics directory (`~/.local/state/homelab-pull/metrics`, or
`GPU_METRICS_DIR`), which the Argus agent's node exporter reads with its textfile collector. A new file is renamed over
the old one, so the collector never reads half of one. Argus uses it to expect the NVIDIA GPU exporter only while
there is an NVIDIA GPU. Where that directory doesn't exist (no pull agent), nothing is written. To check:
`cat ~/.local/state/homelab-pull/metrics/homelab-helios-gpu.prom`, and `homelab_gpu_selected` in Argus' Prometheus.

1. **Plex's Transcoder setting "Hardware transcoding device" on Auto** (Settings → Transcoder, with advanced
   settings shown). A specific device stops working when the GPU changes.
2. **Make the link, then let the stack follow it**, in `.env` and, where the pull agent deploys, in its settings
   (its `COMPOSE_FILE` takes precedence over `.env`). Make the link first: a `COMPOSE_FILE` naming a file that
   doesn't exist stops every `docker compose` command. On the GPU the host has now, switching changes nothing that
   runs: Compose resolves the link to the same file, so Plex isn't recreated.

   ```sh
   scripts/select-gpu.sh                                  # "compose.host-gpu.yaml now points at compose.gpu.yaml"
   sed -i 's/^COMPOSE_FILE=.*/COMPOSE_FILE=compose.yaml:compose.host-gpu.yaml/' .env
   docker compose config --quiet && docker compose up -d --wait   # Plex: "Running", not "Recreated"
   ```

3. **Run it at every boot**, with the user unit from [`deploy/systemd/`](../deploy/systemd/) (it expects the checkout
   at `~/homelab-helios`, like the backup's; lingering on, as for the backups):

   ```sh
   cp deploy/systemd/homelab-helios-gpu.service ~/.config/systemd/user/
   systemctl --user daemon-reload
   systemctl --user enable homelab-helios-gpu.service
   journalctl --user -u homelab-helios-gpu      # after a boot: what it found, and what it changed for Plex and Argus
   readlink compose.host-gpu.yaml               # the override in use
   ```

A user unit can't wait for the system's `docker.service`, so the script waits for Docker itself (up to
`GPU_DOCKER_WAIT`, 300 s). Until it has run, Docker starts Plex as it was: on a host that now has another GPU,
Plex's old container fails to start (an NVIDIA reservation without the GPU) or starts without the GPU, and the
script then recreates it. To check by hand: `ls -l /dev/dri` (an Intel GPU's `renderD*`) or `nvidia-smi`, then
`docker exec plex ls /dev/dri`. A transcode marked "(hw)" in Plex's dashboard shows the GPU in use.

## Where data lives

Every app keeps its data in host directories under one setting, `CONFIG_ROOT`: its settings and database in
`CONFIG_ROOT/<app>/config` (`<app>` is the service's name in `compose.yaml`), and any other folder of the app's
beside it, `CONFIG_ROOT/<app>/<purpose>`. The media library stays where `MEDIA_PATH` says.

| What | Where on the host | In the container |
| --- | --- | --- |
| The media library | `MEDIA_PATH` | `/media` (Plex and AURA) |
| Plex's database, metadata and settings | `CONFIG_ROOT/plex/config` | `/config` |
| Plex's cache | `CONFIG_ROOT/plex/cache` | Plex's `Cache` directory under `/config` |
| Plex's transcodes in progress | `CONFIG_ROOT/plex/transcode` | `/transcode` |
| Tautulli's database and settings | `CONFIG_ROOT/tautulli/config` | `/config` |
| AURA's settings and tokens | `CONFIG_ROOT/aura/config` | `/config` |
| Artwork sets AURA hands to Kometa | `CONFIG_ROOT/kometa/config/aura` | AURA: `/kometa` |
| Kometa's secrets (`.env`), overlays, assets, cache, logs | `CONFIG_ROOT/kometa/config` | `/config` |
| Kometa's configuration and collection files (placeholders only) | `kometa/` in the checkout, read-only | `/config/config.yml`, `/config/<name>.yml` |
| AURA's artwork, read by Kometa | `CONFIG_ROOT/aura/config/auraassets` | Kometa: `/auraassets` |
| ImageMaid's settings | `CONFIG_ROOT/imagemaid/config` | `/config` |
| Kometa Quickstart's database, with the configs and tokens entered in it | `CONFIG_ROOT/quickstart/config` | `/config` |
| Plex's data, cleaned by ImageMaid | `CONFIG_ROOT/plex/config/Library/Application Support/Plex Media Server` | ImageMaid: `/plex` |
| Plex's cache, cleaned by ImageMaid | `CONFIG_ROOT/plex/cache` | ImageMaid: `/plex/Cache` |
| The Dozzle agent's certificate and key (owned by root, not backed up; [below](#dozzles-certificate)) | `CONFIG_ROOT/dozzle/certs` | `/run/secrets/dozzle_cert`, `/run/secrets/dozzle_key`, read-only |

Every mount is listed in [interfaces.md](interfaces.md#volumes-and-mounts).

> [!WARNING]
> **Never point `CONFIG_ROOT` (or any path setting) into `/var/lib/docker/volumes`, and don't keep app data in
> named Docker volumes.** `docker volume prune`, `docker system prune --volumes` and Portainer's "remove unused
> volumes" delete every volume no container mounts *as a volume*, and that includes a volume whose `_data` folder a
> service bind-mounts by its path: Docker counts it as unused. A volume prune deleted a server's Plex database
> that way. Keep all app data in directories under `CONFIG_ROOT`, outside Docker's own directories, where no Docker
> cleanup command reaches it.

## Installing

1. Clone the repository (or download a release's source archive and verify it,
   [verifying-releases.md](verifying-releases.md)).
2. Create `.env` from `.env.example` (mode `600`) and set every value.
3. Create the data directories under `CONFIG_ROOT`, owned by `PUID:PGID` (the
   [quick start](quick-start.md) has the command). Create Kometa's secrets file from `kometa.env.example`, owned by
   `PUID` and readable only by it, and fill in every value:
   `sudo install -m 600 -o <PUID> -g <PGID> kometa.env.example <CONFIG_ROOT>/kometa/config/.env` (the values from
   `.env`). Kometa reads it itself, so the values stay out of the container's environment. Its configuration,
   `kometa/`, holds only `<<UPPER_SNAKE>>` placeholders, which Kometa fills from these `KOMETA_*` values. Put the
   Dozzle agent's certificate and key in `CONFIG_ROOT/dozzle/certs`, owned by root ([below](#dozzles-certificate)).
4. `docker compose up -d`, then check Kometa's configuration with the real values:
   `docker compose run --rm kometa --validate --validate-level full` should end with `Result: PASSED`.

**Adopting existing containers.** If the services already run on the host (from Portainer stacks or another Compose
project), point the stack at their existing data instead of starting empty: stop the old containers, move each service's
data into its directory under `CONFIG_ROOT` (owned by `PUID:PGID`), and keep the same published ports and the **same
container path for the media library**: Plex stores every file's path in its database, so a different mount point makes
it see a new library and rescan everything, losing watch state for files it can't match. Keep the same image family too
(Plex's own or LinuxServer.io's), since they lay out `/config` differently. Take a backup of the old data first.

The maintainer's server runs `main` rather than a release, and deploys every merge by itself
([upgrading.md](upgrading.md#following-main)). For your own setup, a release is the safer choice.

## Dozzle's certificate

The Dozzle agent and the homelab's Dozzle (the hub, on another host) authenticate each other with a certificate and
key: each end presents the pair and accepts only a peer that presents the same one. Every Dozzle image also ships a
built-in pair, the same in every copy, so an agent that uses it accepts anyone on the network who has a Dozzle image,
and through it they can read every container's log and control Docker. This stack never uses the built-in pair: the
agent reads its own from two files under `CONFIG_ROOT/dozzle/certs` (Docker secrets, mounted read-only in
`/run/secrets`), and it doesn't start while either file is missing.

| File | Owner, mode | What |
| --- | --- | --- |
| `CONFIG_ROOT/dozzle/certs/dozzle_cert.pem` | `root:root`, `644` | The certificate (self-signed, valid for five years) |
| `CONFIG_ROOT/dozzle/certs/dozzle_key.pem` | `root:root`, `600` | Its private key: **a secret**; whoever holds it can connect to the agent |

Both belong to root: the agent runs as root without capabilities, so it can read only a file that root owns (or one
that every user can read, which the key must never be).

**One pair for the hub and all its agents.** Make it once, on a machine you trust, with the Dozzle image this stack
pins (the `image:` of `dozzle-agent` in `compose.yaml`):

```sh
mkdir -m 700 dozzle-pair
docker run --rm --network none -v "$PWD/dozzle-pair:/out" amir20/dozzle:<tag>@sha256:<digest> \
  --no-analytics generate-certs --cert-out /out/dozzle_cert.pem --key-out /out/dozzle_key.pem
```

Save both files in a password manager: they are never in the stack's backups (`scripts/backup.sh` copies read-write
mounts only), so that is where a rebuilt host gets them back from. Then copy them to every host that runs the hub or
an agent (for example with `scp` into your home directory) and, in each checkout, put them in place:

```sh
. ./.env
sudo install -d -o root -g root -m 755 "$CONFIG_ROOT/dozzle/certs"
sudo install -o root -g root -m 644 ~/dozzle_cert.pem "$CONFIG_ROOT/dozzle/certs/dozzle_cert.pem"
sudo install -o root -g root -m 600 ~/dozzle_key.pem "$CONFIG_ROOT/dozzle/certs/dozzle_key.pem"
rm ~/dozzle_cert.pem ~/dozzle_key.pem
```

`docker compose logs dozzle-agent` then says `Loaded custom dozzle certificate and key` at each start. The hub and every
agent must hold the same pair: an agent refuses a hub with any other one, and the hub then shows that host as
unavailable. So to change it (before it expires, or at once if the key may have leaked), put the new pair on every
host first, then recreate the hub and each agent with it, one right after the other
(`docker compose up -d --force-recreate dozzle-agent` here): until the last one has it, the hub can't show the hosts whose
pair differs from its own. The logs themselves aren't lost: Docker keeps them, and the hub shows them again once
it reaches the agent.

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
- **The Dozzle agent can read every container's logs and, through the Docker socket, control Docker**, for any
  Dozzle that connects to it with its certificate and key ([Dozzle's certificate](#dozzles-certificate)). Keep the
  key secret, and the agent's port (7007) on the LAN only.
- **Kometa Quickstart only while you use it.** It has no login and holds the tokens entered in it: start it on
  demand, stop it after, never forward port 7171 ([quickstart.md](kometa-quickstart.md)).
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

`scripts/scheduled-backup.sh` takes a backup (`scripts/backup.sh`), copies it to another machine with rsync
(encrypted with age, when `BACKUP_AGE_RECIPIENT` is set), keeps only the newest few in both places and reports to an
Uptime Kuma push monitor. A systemd timer runs it nightly. Every setting is in the optional `backup.env`
([interfaces.md](interfaces.md#backupenv)). The backups hold every login and token: copy them only to a machine you
trust as much as this one, or encrypt the copy (step 3).

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
   archives on every core instead of one; age, to encrypt the copy), and create a key used only for the backups,
   with an alias for it in `~/.ssh/config`:

   ```sh
   sudo apt install -y rsync curl pigz age
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
3. **The encryption key** (optional, recommended), on another machine you trust (not this host):
   `age-keygen -o helios-backup.key`. It prints the public key (`age1...`). Keep the key file where you keep your
   other recovery secrets, such as a password manager, and never copy it to this host: without it no encrypted
   backup off the host can be read, and with it any of them can.
4. **Settings**: `cp backup.env.example backup.env && chmod 600 backup.env`, then set
   `BACKUP_REMOTE=backup-host:/volume1/<folder>`, `BACKUP_AGE_RECIPIENT=age1...` (the public key from step 3; leave
   it empty to copy the backups as they are) and, optionally, the retention and `BACKUP_PING_URL`. For the ping, add
   a monitor of type **Push** in Uptime Kuma with a heartbeat interval of 25 hours, and copy its URL.
5. **Try it**: `scripts/scheduled-backup.sh`. Each service stops only while its own data is copied, and the
   archives are compressed after it has started again. With `BACKUP_AGE_RECIPIENT`, the copy off the host is one
   folder per backup holding only `backup.tar.age` and its `SHA256SUMS`; the backup itself stays readable here, in
   `BACKUP_DIR`.
6. **Schedule it**, with the systemd user units in [`deploy/systemd/`](../deploy/systemd/) (they expect the
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

   Kometa runs at 07:30 (`KOMETA_TIMES`), well after the backup's 01:00 start: the backup stops Plex and Kometa while
   it copies their data, and a backup usually takes under an hour but has taken five when something else loads the
   disk at the same time (a backup of the whole virtual machine, say). If you move either, keep them apart. A Kometa
   run while Plex is stopped finds none of its libraries and does nothing.

On a server that deploys with a pull agent ([upgrading.md](upgrading.md#following-main)), `scripts/backup.sh` and
`scripts/restore.sh` take the agent's lock before they stop anything and keep it until they finish, so a merge
can't be deployed in the middle of a backup or restore (a deploy's `docker compose up -d` would start the service
being copied). If a deploy is running, they wait for it (up to 30 minutes, then fail without stopping anything);
the agent skips its runs while they hold the lock and deploys the merge afterwards. Where the agent has never run,
there is no lock and they don't wait.

Restore a copy from the backup server as [rebuilding.md](rebuilding.md) describes; `scripts/restore.sh` verifies
its `SHA256SUMS` first, and a copy that was cut off has none yet, so it is refused. An encrypted copy is decrypted
first with the private key (`age -d -i helios-backup.key backup.tar.age | tar -x`), which gives the backup directory
`scripts/restore.sh` reads; check the copy's `SHA256SUMS` before that (it is sent last, so a copy that was cut off
has none), as [rebuilding.md](rebuilding.md#an-encrypted-backup) shows.

## Uninstalling

```sh
docker compose down          # stops and removes the containers and the stack's network
```

The data directories under `CONFIG_ROOT` (Plex's cache and transcode directory included) and the media library are
left untouched. Remove them by hand if you no longer want the services' data. To remove the server from your Plex
account as well, do it in Plex's account settings on plex.tv.
