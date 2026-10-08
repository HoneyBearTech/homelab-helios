# Security requirements

What homelab-helios is meant to guarantee, what it leaves to the operator and the services, and where secrets
live. The reasoning behind these requirements is in the [assurance case](assurance-case.md).

> Requirement 5 applies from the first release; the others apply now.

## What homelab-helios protects

1. **Only reviewed versions run.** Every image is pinned as `name:tag@sha256:<digest>`. A registry tag
   that is moved or hijacked doesn't change what `docker compose pull` fetches; a new version arrives only
   as a pull request that changes the digest.
2. **No container gets more of the host than it needs.** No service runs privileged, adds Linux
   capabilities, shares the host's network or PID namespace, or mounts the Docker socket (which is root on
   the host), unless the exception is written into the service as a reasoned label and reviewed: the one
   planned exception is socket-proxy, which holds the socket read-only on autoheal's behalf. The GPU is
   granted as a device reservation through the NVIDIA runtime, not by privilege.
3. **No secrets in the repository.** The services keep their logins, Plex tokens and keys in their own data,
   outside the repository. `.env` holds settings only; Plex's one-time claim token goes in a gitignored
   `plex.env`, and autoheal's optional webhook URL in a gitignored `autoheal.env`. Secret scanning with push protection and a gitleaks scan of the whole history in CI back this up.
4. **No host details in the repository.** It is public: no hostnames, IP addresses, domains, share names or host
   paths are committed. Examples use placeholders.
5. **Releases are verifiable.** Release files are listed in a `SHA256SUMS` signed keylessly by the release
   workflow, with SLSA provenance and an SBOM of the pinned images ([verifying-releases.md](verifying-releases.md)).
6. **Backups don't leak and can't reach the media.** `scripts/backup.sh` writes archives readable only by the
   user who ran it, and `scripts/restore.sh` writes only the mounts the backup's checksummed `MANIFEST` lists and
   the service still has read-write, never the media library or any other path a service excludes with its
   `org.honeybeartech.helios.backup.skip` label.

## Policy

`scripts/check_compose.py` enforces requirements 1 and 2 on the resolved Compose file in CI and
before every release. A service may break a rule only with the label `org.honeybeartech.helios.allow.<rule>` and
a non-empty reason:

| Rule | Fails when a service |
| --- | --- |
| `image` | has no `image` |
| `digest` | uses an image without both a tag and a `sha256` digest |
| `latest` | uses the `latest` tag |
| `build` | builds an image instead of pulling a pinned one |
| `privileged` | sets `privileged: true` |
| `cap-add` | adds Linux capabilities |
| `host-network` / `host-pid` | uses the host's network or PID namespace |
| `docker-socket` | mounts the Docker socket |
| `healthcheck` | has no health check, or disables it (one defined only in the image isn't visible to the check) |

## What it doesn't protect

- **The services themselves.** A vulnerability in Plex, Tautulli, AURA, Kometa or ImageMaid is that project's to fix;
  homelab-helios ships the fixed version once it's released ([dependencies.md](dependencies.md)).
- **Who can watch.** Plex's sign-in, its shared users, its "allowed without authentication" networks and its
  remote access are configured in Plex and stored in its data; deciding them is the operator's job
  ([installing.md](installing.md#running-it-securely)). So is the security of the Plex account that owns the
  server, and of plex.tv itself.
- **Viewing history.** Plex and Tautulli record who watched what and from where. It stays in their data and in
  backups; anyone given Tautulli access sees it.
- **Access to the other web UIs.** Keeping Tautulli and AURA on the LAN, behind a reverse proxy's access lists,
  is the operator's job.
- **Plex's data, to ImageMaid.** ImageMaid mounts Plex's data directory read-write and deletes images Plex no
  longer uses; a faulty version could delete more. Back up before upgrading it, as for Plex.
- **The media library.** Plex and AURA mount it read-write: AURA writes artwork into it, and Plex deletes files
  when its "allow media deletion" option is on. A faulty version or a compromised service could change or delete
  files; only snapshots on the storage that holds the library protect against that, and this stack never backs
  it up.
- **autoheal's reach.** autoheal never holds the socket: `socket-proxy` does, and passes on only listing,
  inspecting, restarting and stopping containers, on an internal network with no published port. Whoever
  controls autoheal or the proxy can still stop any container on the host and read containers' settings,
  including their environment; this stack keeps no secrets in environment variables (Plex's claim token aside,
  which is single-use and short-lived).
- **Restart loops.** autoheal restarts an unhealthy service every few minutes for as long as it stays
  unhealthy; that keeps a hung service available but can hide a real fault. Restarts are logged (and sent to the
  webhook if one is set).
- **The GPU driver and runtime.** The NVIDIA driver and Container Toolkit on the host are trusted and kept up to
  date by the operator.
- **The host.** Anyone with root, `docker` group membership or write access to `.env` or the services' data
  controls the stack; those are trusted.
- **Upstream images' internals.** Some images run as root inside the container; that is the image's design and
  is accepted where the image offers nothing else.

## Where secrets live

| Secret | Where | Never in |
| --- | --- | --- |
| Plex's server token and the account it's linked to | Plex's data (`Preferences.xml`) | the repository, `.env`, issues, logs you paste |
| Plex's claim token (first start only, expires within minutes) | `plex.env`, gitignored, mode `600` | same |
| The Plex token Tautulli uses, Tautulli's login and notification credentials | Tautulli's data | same |
| AURA's Plex token and MediUX token | AURA's data | same |
| Kometa's Plex token and API keys (TMDb and any others you add) | Kometa's `config.yml`, in its data | same |
| ImageMaid's Plex token | ImageMaid's data | same |
| autoheal's webhook URL | `autoheal.env` (mode `600`, gitignored) | same |
| Backups of the data | off the host, mode `600` | anywhere public |
