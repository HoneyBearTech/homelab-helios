# Plan: plex-ls333

## What Sean asked for

"Work all open issues in my repos": here, issue #64, "Plex update available".

## What we found

- `compose.yaml` pins Plex `1.43.5.11079-b3b13e506-ls331`. The issue names
  `ls332`, but linuxserver.io has since published `ls333` (digest
  `sha256:9a1325bf…ac2a`, which is also `latest`). All three are rebuilds of the
  same Plex version, 1.43.5.11079.
- Plex is updated by hand (`docs/dependencies.md`); the last pin, #76, changed
  `compose.yaml` and `CHANGELOG.md`.

## What we'll change

1. `compose.yaml`: pin `lscr.io/linuxserver/plex:1.43.5.11079-b3b13e506-ls333`
   at its index digest. Check: the digest matches on `lscr.io` and `ghcr.io`
   and includes `linux/amd64`; `scripts/plex_watch.py --dry-run` on the branch
   reports it as the newest build.
2. `CHANGELOG.md`: one line, as in #76.
3. Run the repo's lint and tests; CI's policy check and smoke test must pass.
4. Record the job in `docs/` (pass map, decisions log).

Once merged, the weekly watch closes #64 by itself.

## Who's on it

Engineer, Security Officer, Auditor. No Researcher (a one-line pin).

## Risks

Merging deploys at once: Plex restarts on the host, interrupting any stream
for a minute.

## Out of scope

Kometa v2.5.5 (#20): Renovate's next scheduled update group proposes it.
