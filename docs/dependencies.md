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

Each release will carry a CycloneDX SBOM listing every service's image and digest
([verifying-releases.md](verifying-releases.md)).

## Tracking dependencies

- **Dependabot** ([`.github/dependabot.yml`](../.github/dependabot.yml)) checks weekly for new image versions in the Compose file, new tool versions and new Action
  versions, and opens a pull request for each. Dependabot alerts and security updates are on.
- The CI-only images in `run:` steps and the scripts' busybox image aren't seen by Dependabot; they're bumped
  by hand at least every quarter.
- **Patch, minor and major updates merge automatically** once every required check has passed (CI with the Compose
  policy check, the smoke test and the validation of Kometa's configuration against the new Kometa, CodeQL,
  dependency review). That includes Plex, which releases often: it
  can't touch the media library, and its updates often fix security issues.
- **Major updates are read about before they're deployed**, not before they merge: a new major version can
  migrate its data one way, so the service's release notes are read, and a backup taken, before the redeploy
  that brings it to the server ([upgrading.md](upgrading.md#before-you-upgrade)). An update Dependabot can't
  classify waits for the maintainer.
- **A merge doesn't deploy.** The server runs what it last pulled; updates reach it when the operator pulls
  and redeploys, with a backup first ([upgrading.md](upgrading.md)).
- **Dependency review** blocks a pull request that adds or changes a Python or Actions dependency with a known
  vulnerability of moderate severity or higher, or a license outside the allowlist.
- **Nothing updates itself on the host.** Auto-updaters such as Watchtower are not used: they would run
  versions nobody reviewed.

## Policy for vulnerabilities in dependencies

Known vulnerabilities are found through Dependabot alerts, the services' and images' own advisories, and a
weekly scan of the pinned digests (Trivy, HIGH and CRITICAL findings that have a fix, for `linux/amd64`,
reported to code scanning). Each finding is triaged within 14 days:

1. **If a fixed version exists**, bump to it (a Dependabot pull request usually already does) and release.
   A fix for an exploitable critical or high-severity vulnerability goes out in a patch release within 30
   days; others go out with the next release.
2. **If upstream hasn't released a fix**, assess whether it's reachable in this stack (which ports are
   published, and whether anything beyond the LAN can reach them). If it is, mitigate it where possible (for
   example, an access list or not publishing a port) and say so in the release notes; otherwise record the
   reason when dismissing the alert. Either way, it's fixed by a bump when upstream ships one.
3. **If an image is abandoned** and keeps accumulating vulnerabilities, replace it.

### Current findings

Triaged on 2026-10-09, from the scan of `main` at `7e688fc`. Every image was already on its newest upstream
release, so no bump fixes anything yet (step 1); each finding was assessed for reachability instead (step 2),
with the pinned images inspected where the answer depended on how a library is used. The alerts stay open in
code scanning, so they close by themselves when an update ships the fix; none was dismissed. Code scanning
shows a finding that several images share (same package, same rule) as one alert, under the image scanned
last.

| Image | Findings | Assessment |
| --- | --- | --- |
| Plex, autoheal, socket-proxy | none | |
| Tautulli `v2.18.2-ls246`, Kometa `v2.5.2`, Quickstart `v0.10.12` | 4 each, the same Python packages: urllib3 2.7.0 (two), msgpack 1.1.2, setuptools 70.3.0 | Low or not reachable. urllib3's proxy TLS issue needs an HTTPS proxy, and none is configured; its chunk-parser denial of service needs a hostile server among the ones the services call (Plex, metadata APIs) and would stop one run. setuptools' `PackageIndex` isn't used at run time. msgpack crashes only when an `Unpacker` is reused after an error. Tautulli's next LinuxServer.io build (`ls247`) arrives with Dependabot. |
| AURA `v0.9.108` | 8: Next.js 16.3.5 (one **critical**: code execution through `next/og`'s `ImageResponse`; and SSRF in the image optimizer), sharp 0.35.4 (its librsvg), OpenSSL 3.5.7 (QUIC server), undici and brace-expansion inside npm | Not reachable. AURA's build doesn't use `next/og` or `ImageResponse`. Its image optimizer fetches only from the patterns compiled into AURA (its own API), and SVG is off, so librsvg isn't reached through it. Node runs no QUIC server, and npm isn't run. AURA publishes its ports to the LAN only, without a port forward, and runs as `PUID`. Next.js 16.3.6 fixes both; it comes with AURA's next release. |
| ImageMaid `v1.2.0` | 525: 409 in linux-libc-dev, 20 in GitPython 3.1.49, 14 in Pillow 11.2.1, 2 in urllib3 2.6.3, the rest in Debian 13 packages (perl, GnuTLS, OpenSSL, util-linux, curl, Kerberos, and others). The image was last built on 2026-05-02 | Mostly not reachable. linux-libc-dev is kernel headers, and a container runs the host's kernel. GitPython is imported only to read the branch of a git checkout, and the image has none. ImageMaid is Python and talks to Plex through requests, so perl, GnuTLS and curl aren't on its path. **Pillow is the exception**: in `OVERLAYS_ONLY` mode (off by default), ImageMaid opens every unused image in Plex's metadata, and those images come from metadata agents, Kometa and AURA. Leaving that mode off keeps Pillow out of the path. ImageMaid publishes no port, reaches only Plex and runs as `PUID`. |

**Watch: ImageMaid.** Its newest release is from May 2026 and its base image hasn't been rebuilt since. If there
is still no new release at the January 2027 quarterly review, step 3 applies.

## Licenses

homelab-helios's own files are MIT-licensed. The Python tools must be under an OSI-approved license that
dependency review allows (MIT, Apache-2.0, BSD, ISC, PSF, MPL-2.0 and similar); yamllint (GPL-3.0) is
allowed as a development tool. The images keep their own licenses (Plex's is proprietary, see above).

## Policy for findings from static analysis (SAST)

CodeQL analyses the checker and the workflows on every pull request and weekly, and ruff runs the
bandit security rules in CI. A CodeQL finding of medium severity or higher is fixed before the next release, or,
if it is a false positive, dismissed in code scanning with a written reason. A ruff or shellcheck finding fails
CI; a deliberate exception is a per-line `noqa` or `shellcheck disable` with the reason next to it.
