# Pass map

A short record of each piece of work on homelab-helios: what shipped, or what a
review found, and where to look. Newest first. The reasons behind the choices
are in the [decisions log](decisions-log.md); what is planned next is in the
[roadmap](roadmap.md).

## 2026-11-20: `plex-ls333`

Plex pinned to linuxserver.io's build `ls333` of 1.43.5.11079 (a rebuild with
updated base packages; Plex itself unchanged), as the Plex update watch asked
in #64. Digest checked on both registries. Security review clear; code audit
approved.
