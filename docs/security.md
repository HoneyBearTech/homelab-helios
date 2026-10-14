# Security requirements

What homelab-helios is meant to guarantee, what it leaves to the operator and the services, and where secrets
live. The reasoning behind these requirements is in the [assurance case](assurance-case.md).

## What homelab-helios protects

1. **Only reviewed versions run.** Every image is pinned as `name:tag@sha256:<digest>`. A registry tag
   that is moved or hijacked doesn't change what `docker compose pull` fetches; a new version arrives only
   as a pull request that changes the digest.
2. **No container gets more of the host than it needs.** Every service drops every Linux capability and runs
   with `no-new-privileges`, adding back only the few of Docker's default capabilities its image needs
   ([Hardening](#hardening)). No service runs privileged, adds a capability outside Docker's default set, maps a
   host device, shares the host's network or PID namespace, or mounts the Docker socket (which is root on
   the host), unless the exception is written into the service as a reasoned label and reviewed: the two
   exceptions are socket-proxy, which holds the socket read-only on autoheal's behalf, and the Dozzle agent,
   which holds it read-only to read the containers' logs for the homelab's Dozzle. The GPU is granted as a
   device reservation through the NVIDIA runtime, not by privilege.
3. **No secrets in the repository.** The services keep their logins, Plex tokens and keys in their own data,
   outside the repository. `.env` holds settings only; Plex's one-time claim token goes in a gitignored
   `plex.env`, and autoheal's optional webhook URL in a gitignored `autoheal.env`. Secret scanning with push protection and a gitleaks scan of the whole history in CI back this up.
4. **No host details in the repository.** It is public: no hostnames, IP addresses, domains, share names or host
   paths are committed. Examples use placeholders.
5. **Releases are verifiable.** Release files are listed in a `SHA256SUMS` signed keylessly by the release
   workflow, with SLSA provenance and an SBOM of the pinned images ([verifying-releases.md](verifying-releases.md)).
6. **Backups don't leak and can't reach the media.** `scripts/backup.sh` writes archives readable only by the
   user who ran it (the scheduled copy off the host keeps those modes), and `scripts/restore.sh` writes only the mounts the backup's checksummed `MANIFEST` lists and
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
| `no-new-privileges` | doesn't set `security_opt: [no-new-privileges:true]` |
| `cap-drop` | doesn't drop every capability (`cap_drop: [ALL]`) |
| `cap-add` | adds a capability outside Docker's default set (adding back one of those only narrows the default) |
| `host-network` / `host-pid` | uses the host's network or PID namespace |
| `docker-socket` | mounts the Docker socket |
| `devices` | maps a host device into the container (a GPU reservation under `deploy.resources` is allowed: Plex's) |
| `healthcheck` | has no health check, or disables it (one defined only in the image isn't visible to the check) |

## Hardening

What each service runs with, beyond the policy. Every service has `cap_drop: [ALL]` and
`no-new-privileges:true` (the `x-hardened` anchor in `compose.yaml`); the smoke test proves each one still starts
healthy and survives a backup and restore with these settings, with its data directories owned by `PUID:PGID` as
on a host. Each capability added back was proven by starting the image without it.

| Service | Capabilities added back | Read-only root filesystem | Why |
| --- | --- | --- | --- |
| plex | `CHOWN`, `DAC_OVERRIDE`, `SETUID`, `SETGID`, `KILL` | no | Its init (s6-overlay) runs as root: it takes ownership of `/config`, reads Plex's `Preferences.xml` (readable only by Plex's user) and removes a stale pid file after an unclean stop, starts Plex as its own user, and signals it to stop (without `KILL`, every stop waits for Docker's timeout and kills Plex). On a read-only root the init ignores `PUID`/`PGID` and runs Plex as uid 911, which doesn't own the data |
| tautulli | `CHOWN`, `SETUID`, `SETGID`, `KILL` | no | The same init: ownership of `/config`, Tautulli as its own user, a clean stop; writable root for the same reason |
| aura, kometa, quickstart, imagemaid | none | yes (`/tmp` in memory) | They run as `PUID:PGID` and write only their data directories |
| dozzle-agent | none | yes (`/tmp` in memory) | Reads the Docker socket, which belongs to root |
| autoheal | none | yes | Only talks to socket-proxy |
| socket-proxy | none | yes (`/run`, `/tmp` in memory) | Only reads the socket |

Plex's GPU is a device reservation handled by the NVIDIA runtime outside the container, so it needs no
capability; CI has no GPU, so only the host proves it. The Dozzle agent, autoheal and socket-proxy still run as
root inside their containers, since their images offer nothing else; without capabilities that root can only
reach what it owns.

## What it doesn't protect

- **The services themselves.** A vulnerability in Plex, Tautulli, AURA, Kometa, ImageMaid or Kometa Quickstart is that project's to fix;
  homelab-helios ships the fixed version once it's released ([dependencies.md](dependencies.md)).
- **Who can watch.** Plex's sign-in, its shared users, its "allowed without authentication" networks and its
  remote access are configured in Plex and stored in its data; deciding them is the operator's job
  ([installing.md](installing.md#running-it-securely)). So is the security of the Plex account that owns the
  server, and of plex.tv itself.
- **Viewing history.** Plex and Tautulli record who watched what and from where. It stays in their data and in
  backups; anyone given Tautulli access sees it.
- **Access to the other web UIs.** Keeping Tautulli and AURA on the LAN, behind a reverse proxy's access lists,
  is the operator's job. Kometa Quickstart has no login at all: anyone on the LAN can read the tokens in it while
  it runs, so the stack doesn't start it with the others and doesn't restart it after a reboot; running it only
  while it's used, and never beyond the LAN, is the operator's job ([quickstart.md](kometa-quickstart.md)).
- **Plex's data, to ImageMaid.** ImageMaid mounts Plex's data directory read-write and deletes images Plex no
  longer uses; a faulty version could delete more. Back up before upgrading it, as for Plex.
- **The media library.** Plex and AURA mount it read-write: AURA writes artwork into it, and Plex deletes files
  when its "allow media deletion" option is on. A faulty version or a compromised service could change or delete
  files; only snapshots on the storage that holds the library protect against that, and this stack never backs
  it up.
- **Dozzle's access to Docker.** The Dozzle agent needs the Docker socket to read logs; read-only mounting
  doesn't limit the Docker API, so any Dozzle that can reach the agent's port, and anyone who can use that
  Dozzle's web UI, can see every container's logs. It is an allowed exception (label in `compose.yaml`); keep its
  port on the LAN.
- **autoheal's reach.** autoheal never holds the socket: `socket-proxy` does, and passes on only listing,
  inspecting, restarting and stopping containers, on an internal network with no published port. Whoever
  controls autoheal or the proxy can still stop any container on the host and read containers' settings,
  including their environment; this stack keeps no secrets in environment variables (Plex's claim token aside,
  which is single-use and short-lived).
- **Restart loops.** autoheal restarts an unhealthy service every few minutes for as long as it stays
  unhealthy; that keeps a hung service available but can hide a real fault. Restarts are logged (and sent to the
  webhook if one is set).
- **Backups off the host from the host itself.** The scheduled backup can delete old backups on the backup
  server, so whoever controls this host can delete or overwrite them too. Snapshots or a versioned copy on the
  backup server, outside this host's reach, are what protect them; a recycle bin may not see deletions made over
  rsync (Synology's doesn't).
- **The GPU driver and runtime.** The NVIDIA driver and Container Toolkit on the host are trusted and kept up to
  date by the operator. The driver is kept out of unattended upgrades ([rebuilding.md](rebuilding.md#2-the-gpu-driver)),
  so its security updates wait for the operator to install them and reboot; that trades a delay for a GPU that
  doesn't stop working halfway between an update and a reboot.
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
| Kometa's Plex token, API keys (TMDb, OMDb, MDBList, Tautulli, Radarr, Sonarr) and notification webhook | `.env` in Kometa's data, mode `600`; Kometa reads it itself, so the values aren't in the container's environment. `kometa/` holds only placeholders, and a test fails the build otherwise | same |
| ImageMaid's Plex token | ImageMaid's data | same |
| The Plex token and API keys entered in Kometa Quickstart, and the configs built there | Quickstart's data (SQLite); readable by anyone who reaches port 7171 while it runs, since it has no login | same; never forward 7171 |
| autoheal's webhook URL | `autoheal.env` (mode `600`, gitignored) | same |
| Backups of the data | off the host, mode `600` | anywhere public |
| The backup push monitor's URL | `backup.env` (mode `600`, gitignored) | the repository, issues, logs you paste |
| The key for the backup server | the backup user's `~/.ssh` on the host, restricted on the server to this host | same |
