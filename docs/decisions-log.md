# Decisions log

Why things in homelab-helios are the way they are: each entry gives the
decision, the reason, what was considered and not done, and review findings
that were declined, with why. Newest first. What shipped when is in the
[pass map](pass-map.md).

## 2026-11-20: pin Plex build ls333, not the ls332 the issue named

Job `plex-ls333`.

**Decision.** Pin `lscr.io/linuxserver/plex:1.43.5.11079-b3b13e506-ls333` by
its index digest.

**Why.** #64 named `ls332`, but linuxserver.io published `ls333` after the
weekly watch ran; it is the newest build and `latest`. Both are rebuilds of the
same Plex version with updated base packages.

**Not done.** Pinning `ls332` as written (already superseded).

**Review findings.** None declined.
