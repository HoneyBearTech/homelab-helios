# Plan: kometa-2-5-5

## What Sean asked for

Issue #20, "Kometa upstream changes": Kometa v2.5.5 is out.

## What we found

- `compose.yaml` pins `kometateam/kometa:v2.5.4`. v2.5.5 (11 November 2026) is
  the newest release; its index digest `sha256:864cec57…6562` matches the weekly
  watch's report and the registry.
- The watch validated `kometa/` against v2.5.5: passed. The release notes
  touching our setup are bug fixes (Tautulli, filters, IMDb/TMDb mapping) and
  one log fix that stops Sonarr/Radarr API keys appearing in Kometa's logs.
  32-bit ARM images are dropped (helios is x86-64).
- One default we use changed: in `defaults/both/genre.yml`, a "Suspense" genre
  collection no longer uses the Thriller poster (corrected after review: it is
  the artwork map, not which items belong to a collection).
- Renovate lists the update in its scheduled group of minor and patch updates,
  not yet opened. The last Kometa update (#77) was pinned by hand in the same
  way.

## What we'll change

1. `compose.yaml`: pin `kometateam/kometa:v2.5.5` at its index digest. Check:
   the digest matches the registry and lists `linux/amd64`; CI's **Kometa
   config** check validates `kometa/` against it; `scripts/kometa_watch.py
   --dry-run` on the branch reports the pin is current.
2. `CHANGELOG.md`: one line, as in #77, including the genre default change.
3. Run the repo's lint and tests; CI's policy check and smoke test must pass.
4. Record the job in `docs/` (pass map, decisions log).

Once merged, the weekly watch closes #20 and Renovate drops Kometa from its
group.

## Who's on it

Engineer, Security Officer, Auditor. No Researcher (the watch already compared
the release).

## Risks

- Merging deploys at once: the pull agent recreates Kometa and validates it with
  the real values (`docs/kometa.md`). A failed run means going back to v2.5.4
  and restoring Kometa's data.
- A "Suspense" genre collection, if one exists, shows its own poster instead
  of the Thriller one.

## Out of scope

`docs/kometa.md` still says Dependabot proposes Kometa updates (Renovate does
now); noted for the roadmap. The other updates in Renovate's group.
