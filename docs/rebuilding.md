# Rebuilding the host

How to bring the stack back on a new or wiped machine from a backup made by `scripts/backup.sh`
([upgrading.md](upgrading.md#backing-up)), with every service's settings and history as they were.

You need: the backup directory (copied off the old host), this repository, and access to the media library.

## 1. The operating system

Install a 64-bit Linux server; the reference is **Ubuntu 24.04 on amd64**. If it's a virtual machine, pass the
GPU through to it first. Then:

```sh
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y unattended-upgrades git
```

Give the machine the same address the old one had (or update everything that reaches it by address: reverse
proxy hosts, port forwards for Plex's remote access, monitoring, anything that reads Tautulli's or Plex's API).

Mount the media library at the same host path as before (`MEDIA_PATH` in the backup's `.env`).

## 2. The GPU driver

Install the NVIDIA driver as a DKMS build, for example the headless server branch
(`sudo apt install nvidia-headless-<branch>-server nvidia-utils-<branch>-server`; `ubuntu-drivers list --gpgpu`
shows the branches), then reboot and check it with `nvidia-smi`.

Then keep the driver out of unattended upgrades. An update replaces the driver's libraries at once but its kernel
module only at the next reboot, and until then every new GPU container, Plex's included, fails with
"driver/library version mismatch". From the repository (step 4), or with the file fetched from GitHub:

```sh
sudo install -m 644 deploy/apt/51unattended-upgrades-nvidia /etc/apt/apt.conf.d/
apt-config dump Unattended-Upgrade::Package-Blacklist     # lists "^nvidia-" and "^libnvidia-"
```

Kernel updates still install unattended: DKMS builds the installed driver's module for each new kernel. Update
the driver yourself in a quiet window and reboot straight after (`sudo apt update && sudo apt upgrade && sudo
reboot`). The rule doesn't cover a driver installed as prebuilt kernel modules (`linux-modules-nvidia-*`), whose
versions follow the kernel's.

## 3. Docker and the NVIDIA Container Toolkit

Install Docker Engine and the Compose plugin from Docker's own repository, following
[docs.docker.com/engine/install/ubuntu](https://docs.docker.com/engine/install/ubuntu/) (Docker Engine 25 or
later, Compose 2.24 or later). Then the
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html):

```sh
sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker
docker run --rm --gpus all ubuntu nvidia-smi      # the GPU is visible to containers
sudo usermod -aG docker "$USER"                   # equivalent to root on the host; log in again
```

Don't install an auto-updater such as Watchtower ([installing.md](installing.md#running-it-securely)).

## 4. The repository and settings

```sh
git clone https://github.com/HoneyBearTech/homelab-helios.git && cd homelab-helios
git checkout vX.Y.Z      # the release the backup was taken with, or newer; verify it (verifying-releases.md)
cp /path/to/backup/env/.env .env && chmod 600 .env
```

A server that follows `main` ([upgrading.md](upgrading.md#following-main)) stays on `main` here instead
(skip the `git checkout`), and gets its pull agent back once the stack is healthy.

Copy any `<service>.env` from the backup's `env/` the same way (mode `600`); Plex's claim token isn't needed,
since the restored server is already claimed. Edit `.env` if the new host's paths differ (but keep the media
library's container path; `CONFIG_ROOT` never inside `/var/lib/docker/volumes`,
[installing.md](installing.md#where-data-lives)). A backup's `.env` from before `CONFIG_ROOT` has per-app path
settings instead: add `CONFIG_ROOT` and drop those; `scripts/restore.sh` puts each archive where `compose.yaml` mounts
it now. Create the data directories under `CONFIG_ROOT` as your user ([quick start](quick-start.md), step 3), then:

```sh
docker compose config --quiet && docker compose pull
```

## 5. Restore and start

```sh
scripts/restore.sh /path/to/backup    # verifies SHA256SUMS, creates the containers, asks first
docker compose up -d --wait           # waits until every service reports healthy
docker compose ps
```

Then sign in to each service: Plex should list its libraries and watch history under the same server name,
transcode on the GPU, and show up in Plex apps without being added again; Tautulli should show its history and
reach Plex. Plex rebuilds its cache by itself.

## What the backup doesn't bring back

- **Plex's artwork and preview thumbnails, and Kometa's downloaded assets**: left out of backups. Plex shows
  blank posters until it fetches them again (refresh the libraries' metadata); Kometa downloads its assets and
  puts its overlays and the AURA sets saved for it back on its next run (its overlay originals are in the
  backup); sets applied in AURA directly have to be applied again there; Plex regenerates preview thumbnails in
  its scheduled tasks.
- **The media library**: it lives on its own storage, protected there.
- **Host settings**: the static address, the GPU passthrough, the network share's mount, SSH keys, monitoring
  agents.
- **Other machines' view of this one**: reverse proxy hosts, DNS records, router port forwards, anything that
  reaches Helios by address.
- **Services from other projects** on the same host: restore them from their own backups.
