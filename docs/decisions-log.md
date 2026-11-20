# Decisions log

Why things in homelab-helios are the way they are: each entry gives the
decision, the reason, what was considered and not done, and review findings
that were declined, with why. Newest first. What shipped when is in the
[pass map](pass-map.md).

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
