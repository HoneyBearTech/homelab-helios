# Dependencies and vulnerability management

How homelab-helios chooses, obtains, tracks and updates what it's built from, and what happens when one of
those dependencies has a vulnerability.

homelab-helios's dependencies are almost entirely the **container images** it runs, pinned in
`compose.yaml`. The rest are the tools its checks and tests use and the GitHub Actions in its workflows. Its
own code, the policy checker, uses only the Python standard library.

## Choosing a dependency

A new image or tool must:

- be open source under an OSI-approved license (the services' own licenses apply to them: homelab-helios pins
  and runs them, it doesn't redistribute or link them);
- be actively maintained: releases in the last year, security issues answered, and **published for
  `linux/amd64`**, the host's architecture;
- come from the project itself, from its official registry; and
- be worth it: a new service needs a reason in the pull request that adds it.

**Exception: Plex Media Server.** Plex is free to use (hardware transcoding needs a paid Plex Pass) but not open
source. It is accepted because it is the server the household's players already use, and replacing it is a
decision about those players, not about this stack. It runs with no added privileges.

## Obtaining dependencies

| Dependency | Declared in | Pinned by | Fetched by |
| --- | --- | --- | --- |
| The stack's images | `compose.yaml` | version tag and digest | `docker compose pull` |
| Check and test tools (pytest, coverage, ruff, yamllint, shellcheck) | [`requirements-dev.in`](../requirements-dev.in) → [`requirements-dev.txt`](../requirements-dev.txt) | exact version and SHA-256 hashes (`pip-compile --generate-hashes`) | `pip install --require-hashes --no-deps` |
| Helper image for backups and the smoke test (busybox) | [`scripts/lib.sh`](../scripts/lib.sh) | version tag and digest | Docker |
| Kometa's JSON schemas, used only to validate `kometa/` | Kometa's image in `compose.yaml` | that image's release tag | `scripts/kometa-validate.sh` (git), CI (`actions/checkout`) |
| Linters and scanners used only by CI (actionlint, gitleaks, Trivy) | [`.github/workflows/ci.yml`](../.github/workflows/ci.yml), [`scan.yml`](../.github/workflows/scan.yml) | version tag and digest | Docker |
| GitHub Actions | [`.github/workflows/`](../.github/workflows/) | full commit SHA (version in a comment) | GitHub Actions |
| Images of the GitLab copy's pipeline (Python, Docker CLI, git, gitleaks, actionlint) | [`.gitlab-ci.yml`](../.gitlab-ci.yml) | version tag and digest | GitLab Runner (Docker executor) |
| git for the tests on GitLab (`tests/test_post_deploy_check.py` runs it) | the Python image in [`.gitlab-ci.yml`](../.gitlab-ci.yml): the full Debian image, not `-slim` | that image's digest (Debian's git package, as built into the image) | the image; nothing is installed at run time |

Each release carries a CycloneDX SBOM listing every service's image and digest
([verifying-releases.md](verifying-releases.md)).

## Tracking dependencies

- **Renovate** ([`renovate.json`](../renovate.json)) checks Compose images, hash-pinned Python tools in
  `requirements-dev.txt`, GitHub Actions, GitLab pipeline images and the busybox helper in `scripts/lib.sh`.
  Install and authorize the Renovate app for this repository to enable updates. Scheduled updates run before
  6am on Monday in `America/Chicago` and carry the `dependencies` label. Minor and patch updates share one
  group; majors stay separate and carry `major`. CodeQL Action uses are grouped together.
- **Security updates** use OSV vulnerability alerts and the `security` label. Keep Dependabot alerts enabled.
  Renovate replaces Dependabot's version-update configuration; disabling Dependabot security updates is a
  separate maintainer settings follow-up.
- **Every update needs review before merging**, including patch, minor and major versions and image rebuilds
  that change only a digest. Renovate has automerge disabled. Check the release notes and required CI results
  (Compose policy, smoke test, Kometa validation, CodeQL and dependency review), and take a backup before an
  update that can migrate data ([upgrading.md](upgrading.md#following-main)).
- Plex mounts the media library read-write and can delete files when media
  deletion is enabled; follow the [media deletion and storage snapshot
  guidance](installing.md#running-it-securely).
- **Image digests remain required**, alongside version tags. autoheal is the documented exception to specific
  version tags: its maintained build has only `latest`, so its existing digest pin remains required and can
  receive rebuild updates. No image reference changes as part of this migration.
- CI-only image literals in workflow `run:` steps still need manual updates at least every quarter. GitLab
  images and the scripts' busybox image are covered by Renovate. The GitLab pipeline's git comes with its Python
  image, so a newer digest of that image carries Debian's newer git. Review Python updates for preserved hashes
  and successful CI; the unconstrained `requirements-dev.in` source remains unchanged.
- **linuxserver.io images are pinned by their `version-<app version>` tag** (`tautulli:version-v2.18.2@sha256:…`),
  which always points at the newest build of that app version. Dependabot can't follow the build tags
  (`v2.18.2-ls246`): it reads `-ls246` as a suffix that must match exactly, so it never proposes another build. With
  the `version-` tag it proposes both new app versions and rebuilds (a new digest under the same tag). socket-proxy
  uses its bare version tag (`3.4.6`) for the same reason. **Plex is updated by hand:** its version carries a commit
  hash (`1.43.4.10903-e5521bd8c`), which no tag form Dependabot can read, so it keeps its build tag and a new Plex
  release is pinned in its own pull request. A weekly watch
  ([`plex-update-watch.yml`](../.github/workflows/plex-update-watch.yml),
  [`scripts/plex_watch.py`](../scripts/plex_watch.py)) stands in for Dependabot: while linuxserver.io has a newer
  Plex build (a new version or a rebuild), it keeps one issue, **Plex update available**, up to date with the newer
  builds and the latest one's tag and digest, adds one comment per new finding (no repeats), sends the optional
  alert (its own `PLEX_NTFY_URL` or `PLEX_DISCORD_WEBHOOK` repository secret when set, else the Kometa watch's
  `NTFY_URL` or `DISCORD_WEBHOOK`), and closes it once the pin is the newest build. Run it by hand from the Actions
  tab or locally without changing anything: `python3 scripts/plex_watch.py --dry-run`. To check the alert reaches
  its channel, run it from the Actions tab with **Only send a test message** ticked: it sends one test message and
  checks nothing else.
- **A merge deploys.** The maintainer's server follows `main` with a pull agent, so every reviewed merge
  reaches it within about two minutes ([upgrading.md](upgrading.md#following-main)).
- **Dependency review** blocks a pull request that adds or changes a Python or Actions dependency with a known
  vulnerability of moderate severity or higher, or a license outside the allowlist.
- **Nothing on the host updates from a registry.** Auto-updaters such as Watchtower are not used: they would run
  versions nobody reviewed. The pull agent only applies commits merged into `main`.

## Policy for vulnerabilities in dependencies

Known vulnerabilities are found through Dependabot alerts, the services' and images' own advisories, and a
weekly scan of the pinned digests (Trivy, HIGH and CRITICAL findings that have a fix, for `linux/amd64`,
reported to code scanning). Each finding is triaged within 14 days:

1. **If a fixed version exists**, bump to it (a Renovate pull request usually already does) and release.
   A fix for an exploitable critical or high-severity vulnerability goes out in a patch release within 30
   days; others go out with the next release.
2. **If upstream hasn't released a fix**, assess whether it's reachable in this stack (which ports are
   published, and whether anything beyond the LAN can reach them). If it is, mitigate it where possible (for
   example, an access list or not publishing a port) and say so in the release notes; otherwise record the
   reason when dismissing the alert. Either way, it's fixed by a bump when upstream ships one.
3. **If an image is abandoned** and keeps accumulating vulnerabilities, replace it.

### Current findings

Historical October snapshot: triaged on 2026-10-09, from the scan of `main` at `7e688fc`. This table does not
describe today’s pins or establish their current vulnerability status. At that time, every image was on its newest
upstream release, so no bump fixed the findings (step 1); each was assessed for reachability instead (step 2),
with the pinned images inspected where the answer depended on how a library is used. At triage, the alerts were left open in
code scanning rather than dismissed, to close when an update shipped a fix. Code scanning grouped a finding
shared by several images (same package, same rule) under the image scanned last.

| Image | Findings | Assessment |
| --- | --- | --- |
| Plex, autoheal, socket-proxy | none | |
| Tautulli `v2.18.2-ls246`, Kometa `v2.5.2`, Quickstart `v0.10.12` | 4 each, the same Python packages: urllib3 2.7.0 (two), msgpack 1.1.2, setuptools 70.3.0 | Low or not reachable. urllib3's proxy TLS issue needs an HTTPS proxy, and none is configured; its chunk-parser denial of service needs a hostile server among the ones the services call (Plex, metadata APIs) and would stop one run. setuptools' `PackageIndex` isn't used at run time. msgpack crashes only when an `Unpacker` is reused after an error. Tautulli's next LinuxServer.io build (`ls247`) arrives with Dependabot. |
| AURA `v0.9.108` | 8: Next.js 16.3.5 (one **critical**: code execution through `next/og`'s `ImageResponse`; and SSRF in the image optimizer), sharp 0.35.4 (its librsvg), OpenSSL 3.5.7 (QUIC server), undici and brace-expansion inside npm | Not reachable. AURA's build doesn't use `next/og` or `ImageResponse`. Its image optimizer fetches only from the patterns compiled into AURA (its own API), and SVG is off, so librsvg isn't reached through it. Node runs no QUIC server, and npm isn't run. AURA publishes its ports to the LAN only, without a port forward, and runs as `PUID`. Next.js 16.3.6 fixes both; it comes with AURA's next release. |
| ImageMaid `v1.2.0` | 525: 409 in linux-libc-dev, 20 in GitPython 3.1.49, 14 in Pillow 11.2.1, 2 in urllib3 2.6.3, the rest in Debian 13 packages (perl, GnuTLS, OpenSSL, util-linux, curl, Kerberos, and others). The image was last built on 2026-05-02 | Mostly not reachable. linux-libc-dev is kernel headers, and a container runs the host's kernel. GitPython is imported only to read the branch of a git checkout, and the image has none. ImageMaid is Python and talks to Plex through requests, so perl, GnuTLS and curl aren't on its path. **Pillow is the exception**: in `OVERLAYS_ONLY` mode (off by default), ImageMaid opens every unused image in Plex's metadata, and those images come from metadata agents, Kometa and AURA. Leaving that mode off keeps Pillow out of the path. ImageMaid publishes no port, reaches only Plex and runs as `PUID`. |

The October ImageMaid assessment above covered `v1.2.0`. The checked-in Compose pin is now `v1.2.2`; the old
May-build/January-review condition is no longer a current watch assertion. No replacement security assessment
is established here.

## Licenses

homelab-helios's own files are MIT-licensed. The Python tools must be under an OSI-approved license that
dependency review allows (MIT, Apache-2.0, BSD, ISC, PSF, MPL-2.0 and similar); yamllint (GPL-3.0) is
allowed as a development tool. The images keep their own licenses (Plex's is proprietary, see above).

## Policy for findings from static analysis (SAST)

CodeQL analyses the checker and the workflows on every pull request and weekly, and ruff runs the
bandit security rules in CI. A CodeQL finding of medium severity or higher is fixed before the next release, or,
if it is a false positive, dismissed in code scanning with a written reason. A ruff or shellcheck finding fails
CI; a deliberate exception is a per-line `noqa` or `shellcheck disable` with the reason next to it.
