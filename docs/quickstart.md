# Kometa Quickstart

[Kometa Quickstart](https://github.com/Kometa-Team/Quickstart) is a web UI for building and validating Kometa
configurations: it walks through Plex, the libraries, collections, overlays and settings, checks each service's
credentials and writes the YAML. In this stack it is a **tool, started on demand**: `docker compose up -d` doesn't
start it, and it isn't restarted after a reboot.

## Using it

```sh
docker compose --profile tools up -d quickstart   # start it; open http://<host>:7171 from the LAN
docker compose stop quickstart                    # stop it when you're done
```

Inside Quickstart, Plex is at `http://plex:32400` (the stack's network). Its data, including every config built in
it, is in `QUICKSTART_CONFIG_PATH` and survives a stop; `scripts/backup.sh` backs it up like any other service's
data (a Quickstart that has never been started has none and is skipped).

## What it can reach, and who can reach it

- **It has no login.** Anyone who can reach port 7171 while it runs can open it, read the Plex token and API keys
  entered in it, and change its configs. Run it only while you use it, never forward port 7171 at the router, and
  don't give it a name on a reverse proxy without the proxy's own authentication
  ([security.md](security.md#where-secrets-live)).
- **Its configs hold the real values.** A config exported from Quickstart contains the Plex token and API keys:
  never commit it. Bring the parts you want into `kometa/` by hand, with every secret, address and host path as
  its `<<UPPER_SNAKE>>` placeholder (`kometa.env.example` lists them); CI's placeholder test fails otherwise.
- **Don't use its Kometa or ImageMaid runs, or its self-updater.** Quickstart can install Kometa and ImageMaid from
  their GitHub branches into its data directory and run them, and update itself the same way. That code isn't
  pinned, reviewed or scanned like the stack's images; the stack's own Kometa and ImageMaid do the runs.
- It talks to GitHub (Kometa's schemas and defaults), to Plex, and to the services whose credentials it checks.
