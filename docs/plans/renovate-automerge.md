# Plan: renovate-automerge

## What Sean asked for

"Ensure that all my repos that have renovate allow the renovate PRs to auto
merge", on the homelab-atlas model: every update, majors included, merges once
all checks pass, after a 3-day wait.

## What we found

- Renovate's config sets `automerge: false`; the docs disagree with each other
  (some still say Dependabot merges updates automatically).
- Does a merge deploy? Yes: the pull agent applies `main` within minutes.

## What we'll change

1. `renovate.json`: turn on auto-merge for every update, majors included, the
   way homelab-atlas does it: `automerge: true`, squash merges,
   `platformAutomerge: true` (GitHub merges as soon as the required checks
   pass); new versions wait 3 days before they are proposed
   (`minimumReleaseAge`, with `timestamp-optional` so a registry without release
   dates doesn't hold an update forever); security fixes and image rebuilds
   (digest updates) skip the wait. Check: Renovate's config validator passes,
   and a local Renovate dry run shows auto-merge on for ordinary updates and off
   for the exceptions below.
2. Docs that say updates are merged by hand, or by Dependabot: GOVERNANCE.md,
   README.md, docs/dependencies.md, docs/architecture.md, docs/kometa.md (also:
   Renovate, not Dependabot, proposes Kometa updates), docs/assurance-case.md,
   docs/README.md. Say instead that Renovate merges updates once every check
   passes, and name the exceptions.
3. Record the job in `docs/` (pass map, decisions log, roadmap; created if
   missing).

## Kept manual

- Plex stays updated by hand (its build tag isn't something Renovate reads; the
  weekly Plex watch covers it).

Each exception is an earlier decision by the owner; to drop one, say so on this
pull request.

## Who's on it

Engineer, Security Officer, Auditor.

## Risks

- A merge deploys: an update that passes CI but misbehaves on the server reaches
  it unattended. The nightly backup and the pull agent's post-deploy check are
  the safety net.
- Renovate's schedule is unchanged, so updates still arrive once a week.

## Out of scope

Repository settings and branch rules (only the owner changes those), and the
workflows under `.github/workflows` (a leftover Dependabot auto-merge workflow
stays as it is).
