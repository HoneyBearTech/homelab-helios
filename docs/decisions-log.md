# Decisions log

Why things in homelab-helios are the way they are: each entry gives the
decision, the reason, what was considered and not done, and review findings
that were declined, with why. Newest first. What shipped when is in the
[pass map](pass-map.md).

## 2026-11-20: Renovate merges its own pull requests

Job `renovate-automerge` (#101).

**Decision.** Renovate merges its pull requests itself once every check passes,
majors included; new versions wait 3 days, security fixes and image rebuilds
don't, on the model homelab-atlas already uses. Kept manual: Plex stays manual
(its own pull request). `platformAutomerge` is true.

**Why.** The owner asked for every repo with Renovate to merge its updates
automatically (2026-11-20) and chose this model, majors included, over keeping
majors manual.

**Not done.** Repository settings and branch rules (owner only) and workflows
are unchanged. A group merges automatically only when every update in it may, so
each manual exception gets its own pull request.

**Review findings.** Fixed: stale docs that still promised a manual review or
named Dependabot, and (where it applied) exceptions that sat inside the update
group. None declined. Docs that still named Dependabot for the update flow now
say Renovate.

## 2026-11-20: pin Kometa v2.5.5 by hand

Job `kometa-2-5-5`.

**Decision.** Pin `kometateam/kometa:v2.5.5` by its index digest, as #77 did
for v2.5.4.

**Why.** It is the newest release; the weekly watch validated `kometa/`
against it. Renovate had queued it in its scheduled group, not yet opened.

**Not done.** Waiting for Renovate's group (it bundles unrelated updates).
`docs/kometa.md` still says Dependabot proposes Kometa updates; left for a
docs pass (roadmap).

**Review findings.** The code audit showed the `genre.yml` change is to the
poster map, not to which items join a collection; the plan and changelog were
corrected. None declined.

## 2026-11-20: pin Plex build ls333, not the ls332 the issue named

Job `plex-ls333`.

**Decision.** Pin `lscr.io/linuxserver/plex:1.43.5.11079-b3b13e506-ls333` by
its index digest.

**Why.** #64 named `ls332`, but linuxserver.io published `ls333` after the
weekly watch ran; it is the newest build and `latest`. Both are rebuilds of the
same Plex version with updated base packages.

**Not done.** Pinning `ls332` as written (already superseded).

**Review findings.** None declined.
