# Upgrading

A homelab-helios release changes which image versions run, and sometimes the services or settings. Services often
migrate their database when they start a new version and can't go back afterwards (Plex does on many releases),
so **every upgrade starts with a backup**. The same steps apply to updating a checkout of `main`, which is
possible but unsupported for anything you depend on.

> **Planned:** there are no releases yet and no `compose.yaml`. The backup and restore scripts exist and are
> tested against a stand-in stack; they run in CI against the real one once it's added.

## Before you upgrade

1. Read the release notes (the `CHANGELOG.md` section) for every release between yours and the new one, and
   the services' own release notes for any major version bump. Anything under **Upgrading** needs action.
2. Verify the new release ([verifying-releases.md](verifying-releases.md)).
3. Pick a time when nobody is watching: Tautulli's activity page shows current streams. The backup stops the
   stack, and so does the upgrade.

## Backing up

The state worth keeping is each service's data: Plex's database, metadata and settings, Tautulli's database
and settings, AURA's settings, and Kometa's and ImageMaid's configuration. `scripts/backup.sh` stops the stack so the databases are
consistent, archives each of those mounts, copies `.env` and any `<service>.env`, and starts again whatever was
running:

```sh
scripts/backup.sh                       # into backups/<date>-<time>/ in the checkout (gitignored)
scripts/backup.sh /path/to/backup-dir   # or a directory of your choice (new or empty)
```

It **never** archives the media library, Plex's cache or its transcode directory: the library is far too large
and is protected by snapshots on the storage that holds it; the cache and transcodes are disposable. Plex's
metadata and thumbnails are archived, so with a large library the backup can be tens of gigabytes and take a
while; Plex stays stopped until it's done.

The directory holds one `<service>--<path>.tar.gz` per mount, the settings under `env/`, a `MANIFEST` naming
each archive's service, container path, host path and image, and `SHA256SUMS`. Everything in it is readable
only by the user who ran the backup, and it contains Plex tokens. **Copy it off the host.**

## Upgrading

```sh
git fetch --tags
git checkout vX.Y.Z
docker compose pull
docker compose up -d --wait
docker compose ps
```

Then check each service's web UI and logs (`docker compose logs <service>`) for migration errors, that Plex
still lists its libraries and watch history, that one stream transcodes on the GPU (Plex's dashboard shows
"(hw)"), and that Tautulli still reaches Plex.

## Rolling back

If a service fails after the upgrade, go back to the previous version **and** restore its data; a service whose
database was migrated forward may not start with the older image. For one service (Plex here):

```sh
git checkout vPREVIOUS
scripts/restore.sh backups/YYYYMMDD-HHMMSS plex   # checks SHA256SUMS, lists what it replaces, asks first
docker compose up -d plex
```

`scripts/restore.sh` replaces everything in each of the service's mounts listed in the backup's `MANIFEST`,
keeping the files' owners and modes. Without service names it restores every service in the backup. Anything
watched between the backup and the restore drops out of Plex's and Tautulli's history.

## Restoring on a new host

See [rebuilding.md](rebuilding.md): install the host, restore `.env`, then `scripts/restore.sh` creates the
containers and fills their data from the backup.
