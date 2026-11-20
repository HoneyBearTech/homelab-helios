# Pass map

A short record of each piece of work on homelab-helios: what shipped, or what a
review found, and where to look. Newest first. The reasons behind the choices
are in the [decisions log](decisions-log.md); what is planned next is in the
[roadmap](roadmap.md).

## 2026-11-20: `kometa-2-5-5`

Kometa pinned to v2.5.5 by digest, as the weekly Kometa watch asked in #20.
`kometa/` validates unchanged. One default it uses changed: a "Suspense" genre
collection no longer uses the Thriller poster (artwork only). Security review
clear; code audit found one wording error (fixed). Lint and 205 tests pass.

## 2026-11-20: `plex-ls333`

Plex pinned to linuxserver.io's build `ls333` of 1.43.5.11079 (a rebuild with
updated base packages; Plex itself unchanged), as the Plex update watch asked
in #64. Digest checked on both registries. Security review clear; code audit
approved.
