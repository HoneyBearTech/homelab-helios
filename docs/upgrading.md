# Upgrading

A homelab-helios release changes which image versions run, and sometimes the services or settings. Services often
migrate their database when they start a new version and can't go back afterwards (Plex does on many releases), so
**every upgrade starts with a backup**. The same steps apply to updating a checkout of `main` by hand; the
maintainer's server follows `main` automatically instead, where the merge is the upgrade ([Following
`main`](#following-main)).

## Before you upgrade

1. Read the release notes (the `CHANGELOG.md` section) for every release between yours and the new one, and
   the services' own release notes for any major version bump. Anything under **Upgrading** needs action.
2. Verify the new release ([verifying-releases.md](verifying-releases.md)).
3. Pick a time when nobody is watching: Tautulli's activity page shows current streams. The backup stops each
   service for a few minutes, and the upgrade restarts the stack.

## Backing up

The state worth keeping is each service's data: Plex's database, metadata and settings, Tautulli's database
and settings, AURA's settings, and Kometa's and ImageMaid's configuration. `scripts/backup.sh` stops one service at a
time, copies its mounts while it is stopped so its database is consistent, starts it again if it was running, and
then compresses the copy; services with nothing to archive keep running. It also copies `.env` and any
`<service>.env`:

```sh
scripts/backup.sh                       # into backups/<date>-<time>/ in the checkout (gitignored)
scripts/backup.sh /path/to/backup-dir   # or a directory of your choice (new or empty)
```

It **never** archives the media library, Plex's cache or its transcode directory: the library is far too large
and is protected by snapshots on the storage that holds it; the cache and transcodes are disposable. It also
leaves out Plex's artwork (`Metadata`) and preview thumbnails (`Media`) and Kometa's downloaded `assets/` (the
services' `backup.exclude` labels): they are most of the data, and the services re-create them. Plex's databases
are archived, so Plex stays stopped for a few minutes. A restore leaves the left-out paths as they are.
[Scheduled backups](installing.md#scheduled-backups) do this nightly and copy each backup off the host.

The directory holds one `<service>--<path>.tar.gz` per mount, the settings under `env/`, a `MANIFEST` naming
each archive's service, container path, host path and image, `NETWORKS` (the address range of any network the
stack uses but doesn't create, for a rebuild; this stack creates all of its own), `VERSION` (the checkout's
`git describe`) and `SHA256SUMS`. Everything in it is readable only by the user who ran the backup, and it contains
Plex tokens. **Copy it off the host.**

## Upgrading

```sh
git fetch --tags
git checkout vX.Y.Z
docker compose pull
docker compose run --rm kometa --validate --validate-level full   # must end with "Result: PASSED"
docker compose up -d --wait
docker compose up -d --force-recreate kometa                      # when kometa/ changed
docker compose ps
```

The Kometa check is the only one that uses its real secrets: it validates `kometa/` against Plex and the other
services with the new image, before Kometa runs. If it fails, stay on the previous version and fix `kometa/`
first. Kometa's files are single-file mounts, which keep the old file until the container is recreated: hence
`--force-recreate` when `kometa/` changed ([kometa.md](kometa.md#upgrading-kometa-safely)).

Then check each service's web UI and logs (`docker compose logs <service>`) for migration errors, that Plex
still lists its libraries and watch history, that one stream transcodes on the GPU (Plex's dashboard shows
"(hw)"), and that Tautulli still reaches Plex.

## Following `main`

The maintainer's server doesn't check out releases: it runs `main`, and a small pull agent (kept in the
maintainer's private orchestration repository, not here) deploys every merge. A systemd user timer starts it about
every 90 seconds; when `main` has moved, it fast-forwards the checkout, runs `docker compose config --quiet`,
`docker compose pull` and `docker compose up -d --remove-orphans --wait`, and logs the old and the new commit. So
**a merge to `main` reaches the server within about two minutes**, including the updates Dependabot merges by
itself ([dependencies.md](dependencies.md#tracking-dependencies)).

- The agent only fast-forwards: it refuses a checkout with local changes or a `main` whose history was rewritten.
  If the configuration doesn't resolve or an image can't be pulled, it moves the checkout back, so the server keeps
  running what it ran.
- **The merge is the upgrade.** Before merging an update that can migrate a service's data, read the release notes
  and take a backup on the server (`scripts/backup.sh`). The updates that merge by themselves (patch, minor and
  major ones, and image rebuilds) reach the server with only the nightly [scheduled
  backup](installing.md#scheduled-backups) behind them.
- **Kometa is the exception.** The agent doesn't run Kometa's check with the real values, and its `up -d` doesn't
  recreate Kometa when only `kometa/` changed: a single-file mount keeps the old file. After a merge that changes
  `kometa/` or Kometa's image, run on the server `docker compose run --rm kometa --validate --validate-level full`
  (it must end with `Result: PASSED`), then `docker compose up -d --force-recreate kometa`
  ([kometa.md](kometa.md#upgrading-kometa-safely)).
- **Rolling back** is a revert pull request, deployed the same way. If the service already migrated its data,
  restore that too ([Rolling back](#rolling-back)).
- **Holding the server on a version**: check out that commit or release on the server (`git checkout vX.Y.Z`).
  The agent pauses while the checkout isn't on `main`, and carries on once it's switched back (`git switch main`).

## Rolling back

If a service fails after the upgrade, go back to the previous version **and** restore its data; a service whose
database was migrated forward may not start with the older image. For one service (Plex here):

```sh
git checkout vPREVIOUS
scripts/restore.sh backups/YYYYMMDD-HHMMSS plex   # checks SHA256SUMS, lists what it replaces, asks first
docker compose up -d plex
```

On a server that follows `main`, revert the change with a pull request instead of checking out the old release
(the merge deploys the old version), then restore the service's data the same way.

`scripts/restore.sh` replaces everything in each of the service's mounts listed in the backup's `MANIFEST`,
keeping the files' owners and modes. Without service names it restores every service in the backup. Anything
watched between the backup and the restore drops out of Plex's and Tautulli's history.

## Restoring on a new host

See [rebuilding.md](rebuilding.md): install the host, restore `.env`, then `scripts/restore.sh` creates the
containers and fills their data from the backup.
