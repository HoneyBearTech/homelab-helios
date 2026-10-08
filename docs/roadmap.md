# Roadmap

Where homelab-helios is going over roughly the next twelve months (from October 2026). Plans change; this
file changes with them, in the same pull request.

## Now: the stack in git

- Done: the checks, backup and restore scripts, smoke test, release signing and project policies, ported from
  the sibling homelab stacks: backups skip the media library, and the smoke test runs without a GPU.
- Done: `compose.yaml` with Plex, Tautulli, AURA, Kometa and ImageMaid, every image pinned by tag and digest for `linux/amd64`, a
  health check for each service and autoheal (behind a filtering socket proxy) to restart one that turns
  unhealthy, the GPU for Plex as an optional override,
  Dependabot proposing updates.
- Done: the smoke test against the real stack in CI. Next: the first image scan and its triage.
- Done: Kometa Quickstart as an on-demand config editor (not started with the stack, no login, LAN only while it
  runs).
- Done: Kometa's configuration in `kometa/`, with every secret as a placeholder (a test enforces it), mounted
  read-only into Kometa. Next: validating it against Kometa's schemas in CI, a weekly watch for new Kometa
  releases, and `docs/kometa.md`.
- First release (0.1.0) before Helios switches over, so the server is first deployed from a signed, verified
  version.
- Switch Helios to run the stack from a checkout of this repository, adopting the existing data, ports and
  library paths so nothing that reaches the server notices: Plex keeps its libraries, watch history and
  identity, and players don't need to find it again.

## Next: safe upgrades and rebuilds

- Rehearse the documented rebuild ([rebuilding.md](rebuilding.md)) on a scratch machine, including the GPU
  driver and the NVIDIA Container Toolkit.
- Scheduled backups copied off the host.

## Later

- Tighter container settings where the images allow it (read-only root filesystems, dropped capabilities,
  non-root users).
- Optional services as Compose profiles, so a smaller installation can leave them out.

## Security and project health

- Keep CI, CodeQL, Scorecard, dependency review and the DCO check green on every change.
- Branch protection on `main` with required checks; private vulnerability reporting; secret scanning with
  push protection.
- Reach the OpenSSF Best Practices **Passing** and **Silver** badges, and meet **OSPS Baseline** Levels 1
  and 2.
- Signed releases with checksums, SBOM and SLSA provenance from the first release on.

## What homelab-helios will not do

- **Build or patch images.** It runs upstream images unchanged; bugs in the services go to their projects.
- **Configure the services' internals** (Plex's libraries, users and sharing, Tautulli's notifications, Kometa's collections and overlays). Those
  are configured in each service and live in its data, which the backups cover.
- **Manage the media library.** This stack doesn't add, rename or transcode media; the services write only
  artwork (AURA) and, if you allow it, deletions you ask Plex for.
- **Back up the media library.** It is too large; it belongs to the storage that holds it.
- **Store secrets.** No logins, tokens or keys in the repository, encrypted or not.
- **Auto-update.** Every version change is a reviewed commit.
- **Run the other services on the same host** (an inventory app, monitoring agents and log storage). They have
  their own setup, even where they share the host.
- **Be a general-purpose homelab distribution.** It describes one server; others are welcome to fork or borrow
  from it, but options that only another setup needs are out of scope.
