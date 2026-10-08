"""Kometa's committed configuration holds no secrets or host facts, only <<UPPER_SNAKE>> placeholders.

gitleaks doesn't reliably recognise a Plex token or a TMDb key, so every value under a key that holds a
credential, an address or a host path must be a placeholder that Kometa fills from KOMETA_<NAME>.
"""

import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import yaml

if TYPE_CHECKING:
    from collections.abc import Iterator

ROOT = Path(__file__).parent.parent
KOMETA = ROOT / "kometa"
ENV_EXAMPLE = ROOT / "kometa.env.example"
BAD = Path(__file__).parent / "fixtures" / "kometa-bad"

PLACEHOLDER = re.compile(r"<<([A-Z][A-Z0-9_]*)>>")
# Keys whose values are credentials, addresses or host paths, in any section.
SECRET_KEY = re.compile(
    r"(token|apikey|api_key|client_id|client_secret|password|url|root_folder_path|plex_path|radarr_path|"
    r"sonarr_path)$",
    re.IGNORECASE,
)
# Sections whose every value is secret (notification URLs).
SECRET_SECTION = {"webhooks"}
# KOMETA_<NAME> variables Kometa v2.5.2 reads as its own settings (kometa.py: the run options and their aliases,
# Plex's URL and token, Docker detection). It never fills a placeholder from them, so <<NAME>> would stay empty.
RESERVED = {
    "COLLECTION", "COLLECTIONS", "COLLECTIONS_ONLY", "COLLECTION_ONLY", "CONFIG", "DEBUG", "DELETE",
    "DELETE_COLLECTION", "DELETE_COLLECTIONS", "DELETE_COLLECTIONS_LABELS", "DELETE_COLLECTION_LABEL",
    "DELETE_LABEL", "DELETE_LABELS", "DIVIDER", "DOCKER", "IGNORE_GHOST", "IGNORE_SCHEDULES", "IMAGE_DIGEST",
    "LIBRARIES", "LIBRARIES_ONLY", "LIBRARY", "LIBRARY_ONLY", "LINUXSERVER", "LOG_REQUEST", "LOG_REQUESTS",
    "LOW_PRIORITY", "METADATA", "METADATAS_ONLY", "METADATA_FILES", "METADATA_ONLY", "NO_COUNTDOWN", "NO_MISSING",
    "NO_REPORT", "NO_VERIFY_SSL", "OPERATION", "OPERATIONS", "OPERATIONS_ONLY", "OPERATION_ONLY", "OVERLAY",
    "OVERLAYS", "OVERLAYS_ONLY", "OVERLAY_ONLY", "PLAYLISTS_ONLY", "PLAYLIST_ONLY", "PLEX_TOKEN", "PLEX_URL",
    "PROFILE", "READ_ONLY_CONFIG", "RESUME", "RUN", "RUN_COLLECTION", "RUN_COLLECTIONS", "RUN_FILE", "RUN_FILES",
    "RUN_LABEL", "RUN_LIBRARIES", "RUN_LIBRARY", "RUN_METADATA_FILES", "RUN_TEST", "RUN_TESTS", "SCHEMA_PATH",
    "TEST", "TESTS", "TIME", "TIMEOUT", "TIMES", "TIMING", "TIMINGS", "TRACE", "VALIDATE", "VALIDATE_CONFIG",
    "VALIDATE_DIR", "VALIDATE_DIRECTORY", "VALIDATE_FILE", "VALIDATE_FILES", "VALIDATE_LEVEL", "VALIDATE_SCHEMA",
    "VALIDATE_SCHEMAS", "WIDTH",
}  # fmt: skip


def load(path: Path) -> object:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def problems(node: object, path: str = "", *, secret: bool = False) -> Iterator[str]:
    """Yield the path of every secret-bearing value that isn't a usable placeholder."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from problems(
                value,
                f"{path}.{key}" if path else str(key),
                secret=secret or str(key).lower() in SECRET_SECTION or bool(SECRET_KEY.search(str(key))),
            )
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from problems(value, f"{path}[{i}]", secret=secret)
    elif secret:
        match = PLACEHOLDER.fullmatch(node) if isinstance(node, str) else None
        if not match:
            yield f"{path}: not a <<UPPER_SNAKE>> placeholder"
        elif match.group(1) in RESERVED:
            yield f"{path}: KOMETA_{match.group(1)} is one of Kometa's own settings"


def placeholders(path: Path) -> set[str]:
    return set(PLACEHOLDER.findall(path.read_text(encoding="utf-8")))


KOMETA_FILES = sorted(KOMETA.glob("*.yml"))


def test_kometa_files_exist() -> None:
    assert KOMETA / "config.yml" in KOMETA_FILES


@pytest.mark.parametrize("path", KOMETA_FILES, ids=lambda p: p.name)
def test_secrets_are_placeholders(path: Path) -> None:
    assert list(problems(load(path))) == []


def test_bad_fixture_is_caught() -> None:
    assert sorted(problems(load(BAD / "config.yml"))) == [
        "libraries.Movies.radarr.root_folder_path: not a <<UPPER_SNAKE>> placeholder",
        "libraries.Movies.radarr.token: not a <<UPPER_SNAKE>> placeholder",
        "plex.token: KOMETA_PLEX_TOKEN is one of Kometa's own settings",
        "plex.url: not a <<UPPER_SNAKE>> placeholder",
        "tautulli.apikey: not a <<UPPER_SNAKE>> placeholder",
        "tmdb.apikey: not a <<UPPER_SNAKE>> placeholder",
        "webhooks.error: not a <<UPPER_SNAKE>> placeholder",
        "webhooks.run_end[0]: not a <<UPPER_SNAKE>> placeholder",
    ]


def test_env_example_lists_every_placeholder_empty() -> None:
    lines = [line for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines() if line.startswith("KOMETA_")]
    names = {line.split("=", 1)[0].removeprefix("KOMETA_") for line in lines}
    used = set().union(*(placeholders(path) for path in KOMETA_FILES)) - {"UPPER_SNAKE"}
    assert names == used
    assert all(line.endswith("=") for line in lines), "kometa.env.example must not hold values"


def test_every_file_is_linked_from_config() -> None:
    # Kometa's --validate-dir and --validate-file don't check files in v2.5.2; validating config.yml checks
    # the files it links, so a file that isn't linked would go unvalidated.
    text = (KOMETA / "config.yml").read_text(encoding="utf-8")
    unlinked = [p.name for p in KOMETA_FILES if p.name != "config.yml" and f"file: config/{p.name}" not in text]
    assert unlinked == []
