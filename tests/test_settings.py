import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
CONFIG_ROOT = "${CONFIG_ROOT:?set CONFIG_ROOT in .env}"
# Each app's host folders, as container path -> folder under CONFIG_ROOT (owner's layout, 2026-10-15). A mount whose
# folder belongs to another app (AURA's /kometa, Kometa's /auraassets, ImageMaid's /plex) is listed with the app it
# borrows from.
DATA_MOUNTS = {
    "plex": {
        "/config": "plex/config",
        "/config/Library/Application Support/Plex Media Server/Cache": "plex/cache",
        "/transcode": "plex/transcode",
    },
    "tautulli": {"/config": "tautulli/config"},
    "aura": {"/config": "aura/config", "/kometa": "kometa/config/aura"},
    "kometa": {"/config": "kometa/config", "/auraassets": "aura/config/auraassets"},
    "quickstart": {"/config": "quickstart/config"},
    "imagemaid": {
        "/config": "imagemaid/config",
        "/plex": "plex/config/Library/Application Support/Plex Media Server",
        "/plex/Cache": "plex/cache",
    },
}
# Mounts that aren't an app's data: the media library and the Docker socket (each checked by its own rules).
OTHER_SOURCES = ("${MEDIA_PATH:?set MEDIA_PATH in .env}", "/var/run/docker.sock")


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def compose() -> dict:
    return yaml.safe_load(read("compose.yaml"))


def mounts(service: dict) -> list[tuple[str, str]]:
    """(source, target) of each of a service's mounts, short or long syntax, without a trailing :ro."""
    result = []
    for volume in service.get("volumes") or []:
        if isinstance(volume, dict):
            result.append((volume["source"], volume["target"]))
        else:
            # A ${VAR:?message} in the source has colons of its own: split after its closing brace.
            start = volume.find("}") + 1
            source, _, rest = volume[start:].partition(":")
            result.append((volume[:start] + source, rest.split(":")[0]))
    return result


def test_every_setting_is_in_env_example_and_interfaces() -> None:
    used = {
        name
        for path in ("compose.yaml", "compose.gpu.yaml", "compose.intel.yaml", "compose.cpu.yaml")
        for name in re.findall(r"\$\{([A-Z][A-Z0-9_]*)", read(path))
    }
    example = set(re.findall(r"^#? ?([A-Z][A-Z0-9_]*)=", read(".env.example"), re.MULTILINE))
    table = re.findall(r"^\| (`[A-Z][^|]*) \|", read("docs/interfaces.md"), re.MULTILINE)
    documented = {name for cell in table for name in re.findall(r"`([A-Z][A-Z0-9_]*)`", cell)}
    assert used <= example
    assert used <= documented
    # Every setting .env.example offers is read by the stack (COMPOSE_FILE by Docker Compose itself).
    assert example - {"COMPOSE_FILE"} <= used


def test_the_old_per_app_path_settings_are_gone() -> None:
    old = re.compile(r"\b[A-Z]+_(CONFIG|CACHE|TRANSCODE)_PATH\b")
    for path in ("compose.yaml", ".env.example", "docs/interfaces.md", "docs/installing.md", "README.md"):
        assert not old.search(read(path)), path


def test_each_apps_data_mounts_come_from_config_root() -> None:
    services = compose()["services"]
    for app, expected in DATA_MOUNTS.items():
        found = {
            target: source
            for source, target in mounts(services[app])
            if source not in OTHER_SOURCES and not source.startswith("./kometa/")
        }
        assert found == {target: f"{CONFIG_ROOT}/{folder}" for target, folder in expected.items()}, app


def test_kometa_files_stay_mounted_read_only_over_its_config() -> None:
    volumes = compose()["services"]["kometa"]["volumes"]
    files = sorted(path.name for path in (ROOT / "kometa").glob("*.yml"))
    assert files
    for name in files:
        assert f"./kometa/{name}:/config/{name}:ro" in volumes


def test_every_service_with_data_is_listed_and_nothing_else_mounts_a_host_path() -> None:
    for name, service in compose()["services"].items():
        for source, target in mounts(service):
            if source in OTHER_SOURCES or source.startswith("./kometa/"):
                continue
            assert name in DATA_MOUNTS, f"{name} mounts {target} from {source}: add it to DATA_MOUNTS"


def test_no_named_volumes() -> None:
    config = compose()
    assert "volumes" not in config
    for name, service in config["services"].items():
        for source, target in mounts(service):
            assert source.startswith(("/", "./", "${")), f"{name} mounts a named volume at {target}: {source}"


def test_mounts_parses_both_syntaxes() -> None:
    service = {
        "volumes": [
            "${CONFIG_ROOT:?set CONFIG_ROOT in .env}/a/config:/config",
            "./kometa/x.yml:/config/x.yml:ro",
            "/var/run/docker.sock:/var/run/docker.sock:ro",
            {"type": "bind", "source": "/src", "target": "/dst"},
        ],
    }
    assert mounts(service) == [
        ("${CONFIG_ROOT:?set CONFIG_ROOT in .env}/a/config", "/config"),
        ("./kometa/x.yml", "/config/x.yml"),
        ("/var/run/docker.sock", "/var/run/docker.sock"),
        ("/src", "/dst"),
    ]
