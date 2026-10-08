# Quick start

You need a Linux host on amd64 (the reference is Ubuntu 24.04) with Docker Engine and the Compose v2 plugin, a
user in the `docker` group, and, for hardware transcoding, an NVIDIA GPU with its driver, the NVIDIA Container
Toolkit and a Plex Pass ([installing.md](installing.md#requirements)).

1. **Get the stack.**

   ```sh
   git clone https://github.com/HoneyBearTech/homelab-helios.git && cd homelab-helios
   ```

   Once releases exist, check out the latest one (`git checkout vX.Y.Z`) and verify it first
   ([verifying-releases.md](verifying-releases.md)).

2. **Configure it.**

   ```sh
   cp .env.example .env && chmod 600 .env
   ```

   In `.env`, set `TZ`, `PUID`/`PGID` (a user that can read and write your media library), `MEDIA_PATH` and the data
   paths. Every setting is described in [interfaces.md](interfaces.md#settings). For a new Plex server (not one
   you're adopting), put a claim token from [plex.tv/claim](https://www.plex.tv/claim/) in `plex.env` just
   before step 5; it expires within minutes.

3. **Create the data directories** as your user, so Docker doesn't create them owned by root:

   ```sh
   . ./.env && mkdir -p "$PLEX_CONFIG_PATH" "$PLEX_CACHE_PATH" "$PLEX_TRANSCODE_PATH" \
     "$TAUTULLI_CONFIG_PATH" "$AURA_CONFIG_PATH" "$KOMETA_CONFIG_PATH" \
     "$IMAGEMAID_CONFIG_PATH" "$QUICKSTART_CONFIG_PATH"
   ```

4. **Check the GPU** is visible to containers, and let Plex use it:

   ```sh
   docker run --rm --gpus all ubuntu nvidia-smi
   echo 'COMPOSE_FILE=compose.yaml:compose.gpu.yaml' >> .env
   ```

5. **Check and start.**

   ```sh
   docker compose config --quiet   # the file resolves with your settings
   docker compose up -d --wait     # waits until every service reports healthy
   docker compose ps
   ```

6. **Finish each service's setup in its web UI** (ports in [interfaces.md](interfaces.md#services-and-ports)).
   In Plex, add libraries from the media mount and turn on hardware transcoding; in Tautulli, connect it to
   Plex; in AURA, connect it to Plex and MediUX. Write Kometa's `config.yml` and ImageMaid's settings in their data
   directories (each project documents its own). All of them hold tokens afterwards: keep their data private.

To upgrade later, follow [upgrading.md](upgrading.md); it starts with a backup.
