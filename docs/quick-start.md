# Quick start

You need a Linux host on amd64 (the reference is Ubuntu 24.04), Docker Engine and the Compose v2 plugin, and a
user in the `docker` group. Choose CPU, NVIDIA or Intel operation below; hardware transcoding also needs a Plex
Pass ([requirements](installing.md#requirements)). These are operator instructions for your host.

1. **Get the stack.**

   ```sh
   git clone https://github.com/HoneyBearTech/homelab-helios.git && cd homelab-helios
   ```

   To run a release, check out the latest one (`git checkout vX.Y.Z`) and verify it first
   ([verifying-releases.md](verifying-releases.md)); or stay on `main`, which the maintainer's own server follows
   ([upgrading.md](upgrading.md#following-main)). If adopting existing services, first take a backup and follow
   the data migration and image-family precautions in [installing.md](installing.md#installing). Their existing
   configured data can satisfy step 6; do not reset or re-claim an adopted server.

2. **Configure it.**

   ```sh
   cp .env.example .env && chmod 600 .env
   ```

   In `.env`, set `TZ`, `PUID`/`PGID` (a user that can read and write your media library), `MEDIA_PATH`,
   `CONFIG_ROOT` and the schedules. Never keep app data inside `/var/lib/docker/volumes`
   ([why](installing.md#where-data-lives)). See [settings](interfaces.md#settings).

3. **Create the data directories** before Docker can create them owned by root:

   ```sh
   CONFIG_ROOT=$(sed -n 's/^CONFIG_ROOT=//p' .env) && mkdir -p "$CONFIG_ROOT"/plex/{config,cache,transcode} \
     "$CONFIG_ROOT"/{tautulli,imagemaid,quickstart}/config \
     "$CONFIG_ROOT"/aura/config/auraassets "$CONFIG_ROOT"/kometa/config/aura
   ```

   These app directories must belong to `PUID:PGID`. If your shell user has different IDs, arrange that ownership
   explicitly before startup. Create Kometa's protected file from [`kometa.env.example`](../kometa.env.example):

   ```sh
   sudo install -m 600 -o <PUID> -g <PGID> kometa.env.example <CONFIG_ROOT>/kometa/config/.env
   ```

   Replace the angle-bracket placeholders with your local settings. Complete its credentials in step 7, after
   a new Plex/Tautulli instance is initialized. The Dozzle agent also needs its certificate and key in
   `CONFIG_ROOT/dozzle/certs`, owned by root, before full-stack startup in step 8; it cannot start without them
   ([certificate commands](installing.md#dozzles-certificate)).

4. **Choose the transcoding configuration.** Set just one applicable `COMPOSE_FILE` choice in `.env`.

   - **CPU:** leave `COMPOSE_FILE` unset and use `compose.yaml` alone; no GPU override or toolkit is needed.
   - **NVIDIA:** install the NVIDIA driver and Container Toolkit 1.18+, using Docker Engine 29.2+
     ([GPU setup](installing.md#the-gpu-and-docker-292)). Test container access and select the override:

     ```sh
     docker run --rm --gpus all ubuntu nvidia-smi
     echo 'COMPOSE_FILE=compose.yaml:compose.gpu.yaml' >> .env
     ```

   - **Intel:** use the kernel's i915 or xe driver and firmware, verify its render node is available under
     `/dev/dri`, and select the device-mapping override; no NVIDIA toolkit or test is needed:

     ```sh
     echo 'COMPOSE_FILE=compose.yaml:compose.intel.yaml' >> .env
     ```

   For a host whose GPU changes at boot, the optional [boot selector](installing.md#the-gpu-at-boot) can choose
   the override instead.

5. **Check and start only Plex and Tautulli.** For a new Plex server, put a just-issued claim token from
   [plex.tv/claim](https://www.plex.tv/claim/) into gitignored `plex.env` (mode `600`, template
   [`plex.env.example`](../plex.env.example)) immediately before its first start; it expires within minutes.
   An adopted, already claimed server does not need one.

   ```sh
   docker compose config --quiet
   docker compose up -d --wait plex tautulli
   ```

   Neither service depends on Kometa or ImageMaid in Compose, so this leaves both scheduled services unstarted.

6. **Initialize Plex and Tautulli** in their web UIs ([ports](interfaces.md#services-and-ports)). Claim/configure
   the new Plex server and add the libraries expected by the checked-in [Kometa configuration](kometa.md).
   Enable hardware transcoding only for the NVIDIA or Intel branch. Finish Tautulli's setup, connect it to Plex
   and enable its login. Only then obtain the Plex server token and Tautulli API key locally. The one-time
   `PLEX_CLAIM` token differs from `KOMETA_PLEX_SERVER_TOKEN`; empty `plex.env` after claiming. Never print or
   record credentials in shared output. For adopted data, verify the existing libraries, setup and availability
   instead of repeating initialization.

7. **Complete the scheduled services' settings locally.** Fill every placeholder value in
   `CONFIG_ROOT/kometa/config/.env`, including `KOMETA_PLEX_SERVER_TOKEN` and `KOMETA_TAUTULLI_APIKEY`. Retain
   ownership `PUID:PGID` and mode `600`. The template lists required API keys, service URL names and library/root
   folder path names; follow [Kometa's configuration](kometa.md) and verify the configured external integrations
   are available and the library/path names match. This stack does not provision those integrations. Kometa
   reads this file itself, separately from root Compose `.env`. Its `config.yml` and collection files are mounted
   read-only from `kometa/` in the checkout; do not write a replacement config in the ignored data directory.
   Prepare ImageMaid's own settings, including its Plex connection, in `CONFIG_ROOT/imagemaid/config` before
   starting it.

8. **Validate before starting the scheduled services.** With Plex and Tautulli running, every Kometa value
   filled and its required integrations available:

   ```sh
   docker compose run --rm kometa --validate --validate-level full
   ```

   Require `Result: PASSED`; resolve failures before proceeding. Once all prerequisites, including Dozzle's
   certificate files from step 3 and ImageMaid's settings, are ready:

   ```sh
   docker compose up -d --wait
   docker compose ps
   ```

   Complete AURA's local web UI setup, connecting it to Plex and MediUX. Quickstart remains an optional,
   on-demand tool ([Kometa Quickstart](kometa-quickstart.md)). Keep all service data private: it holds tokens.

To upgrade later, follow [upgrading.md](upgrading.md); it starts with a backup.
