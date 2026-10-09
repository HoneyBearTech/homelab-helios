# Kometa's configuration

Kometa's configuration lives in this repository, in [`kometa/`](../kometa/): `config.yml` and the collection files it
links. Each file is mounted read-only over `/config/<name>` in the container, and `KOMETA_READ_ONLY_CONFIG` stops
Kometa from trying to rewrite `config.yml`. Everything Kometa writes (logs, its cache, assets, overlays, reports)
stays in its data directory, `KOMETA_CONFIG_PATH`.

## Secrets: placeholders and Kometa's `.env`

Every secret and host fact in `kometa/` is a placeholder, `<<UPPER_SNAKE>>`, which Kometa fills from the environment
variable `KOMETA_UPPER_SNAKE`: Plex's address and token, the API keys, the notification webhook, and Radarr's and
Sonarr's addresses, keys and root folders.

- The values go in `.env` in Kometa's data directory, created from [`kometa.env.example`](../kometa.env.example),
  which lists every name with a comment:
  `sudo install -m 600 -o <PUID> -g <PGID> kometa.env.example <KOMETA_CONFIG_PATH>/.env`. Kometa reads that file
  itself when it starts, so the values never enter the container's environment (`docker inspect` doesn't show
  them). Backups include it, as they include the rest of Kometa's data.
- A placeholder whose variable isn't set silently becomes empty, and `<<lower_snake>>` is never filled.
- Plex's placeholders are `PLEX_SERVER_URL` and `PLEX_SERVER_TOKEN`: Kometa reads `KOMETA_PLEX_URL` and
  `KOMETA_PLEX_TOKEN` as its own settings and never fills a placeholder from them (nor from any other name it
  reserves).

A test ([`tests/test_kometa_placeholders.py`](../tests/test_kometa_placeholders.py), part of `make test` and CI)
fails the build when a value under a credential, address or path key isn't a placeholder, when a placeholder uses a
reserved name, when `kometa.env.example` doesn't list exactly the placeholders in use, or when a file in `kometa/`
isn't both linked from `config.yml` and mounted in `compose.yaml`. To add a collection file: put it in `kometa/`,
link it as `file: config/<name>.yml`, and add its read-only mount to the `kometa` service.

[Kometa Quickstart](quickstart.md) can help build a configuration, but what it exports holds the real values: bring
the parts you want into `kometa/` by hand, as placeholders.

## How CI checks it

The **Kometa config** job ([`scripts/kometa-validate.sh`](../scripts/kometa-validate.sh); `make kometa` runs the
same locally) validates `kometa/` with the Kometa image pinned in `compose.yaml` and the JSON schemas from the same
release (the image doesn't ship them; without them Kometa skips schema validation and passes). It needs no
secrets: it validates a copy with a dummy value for each placeholder. It passes only if Kometa exits 0, prints
`Result: PASSED` (without network Kometa gives up, exits 0 and prints no result) and reports no unknown keys (Kometa
itself only lists those). Validating `config.yml` checks every file it links. Two deliberately broken fixtures in
[`tests/fixtures/kometa-invalid/`](../tests/fixtures/kometa-invalid/) prove that the job fails when it should.

What it can't catch: a value Plex rejects at run time, such as a filter attribute used under `plex_search`. Only a
real run, or `--validate-level full` with the real values on the server (below), finds those.

## The weekly upstream watch

Every Monday, [the upstream watch](../.github/workflows/kometa-upstream-watch.yml)
([`scripts/kometa_watch.py`](../scripts/kometa_watch.py)) compares the pinned Kometa with Kometa's latest release.
While they differ, or `kometa/` doesn't validate against the latest, it keeps one issue, **Kometa upstream
changes**, up to date with the newer releases, the validation of `kometa/` against the latest one, the release-note
lines that name a key or default the configuration uses (or deprecate, remove or rename something), and the diff
of the Kometa defaults it references.

- **No repeats.** The issue keeps the state it reported in a hidden comment: tags, digest, and hashes of the
  validation report and the diff. A week with nothing new changes nothing: no edit, no comment, no alert. Something
  new rewrites the issue and adds one comment.
- **It closes itself** once `compose.yaml` pins the latest release and `kometa/` validates against it, and reopens
  the same issue when they diverge again.
- **Alerts** (optional): set the repository secret `NTFY_URL` (an ntfy topic URL) or `DISCORD_WEBHOOK`, and a new
  finding also sends a short message there.
- Run it by hand from the Actions tab (**Kometa upstream watch → Run workflow**), or locally without changing
  anything: `python3 scripts/kometa_watch.py --dry-run`.

Dependabot proposes the update itself; the watch is the early warning, with the release notes and the defaults' diff.

## Upgrading Kometa safely

1. Dependabot opens a pull request with Kometa's new tag and digest. It merges automatically once every required
   check passes, **Kometa config** included: a release that rejects `kometa/` doesn't merge.
2. A merge never deploys. On the server, follow [upgrading.md](upgrading.md): back up (`scripts/backup.sh`), check
   out the new version, then check Kometa's configuration with the real values before starting it:

   ```sh
   docker compose pull kometa
   docker compose run --rm kometa --validate --validate-level full   # the only check with the real values
   docker compose up -d --force-recreate kometa
   ```

   `--validate-level full` must end with `Result: PASSED`. `--force-recreate` matters when only `kometa/` changed:
   a single-file mount keeps the old file until the container is recreated.
3. If the next run goes wrong, go back to the previous version and restore Kometa's data
   (`scripts/restore.sh <backup> kometa`): a new Kometa may migrate its cache.

This applies once the server runs the stack from this repository; until then Kometa runs from its old setup there.
