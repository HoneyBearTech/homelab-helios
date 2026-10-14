"""Kometa settings that fixed a bug stay in place.

Each test holds one fix from the CHANGELOG, so reverting the setting fails CI instead of breaking a library again.
"""

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import yaml

if TYPE_CHECKING:
    from collections.abc import Iterator

KOMETA = Path(__file__).parent.parent / "kometa"
REFRESH_FILES = ["movies_refresh.yml", "tv_refresh.yml"]


def load(path: Path) -> object:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def arr_connections(node: object, path: str = "") -> Iterator[tuple[str, dict[str, object]]]:
    """Yield every radarr and sonarr block, the global ones and each library's own, with its path."""
    if isinstance(node, dict):
        for key, value in node.items():
            where = f"{path}.{key}" if path else str(key)
            if key in {"radarr", "sonarr"} and isinstance(value, dict):
                yield where, value
            yield from arr_connections(value, where)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from arr_connections(item, f"{path}[{index}]")


def test_no_arr_connection_monitors_existing_items() -> None:
    # PR #15: with monitor_existing true, Kometa applied its monitor setting (none for Sonarr, false for Radarr)
    # to every existing series or movie its collections matched, and airing shows were unmonitored in Sonarr.
    connections = list(arr_connections(load(KOMETA / "config.yml")))
    assert connections, "config.yml has no radarr or sonarr block"
    wrong = [where for where, block in connections if block.get("monitor_existing") is not False]
    assert not wrong, f"monitor_existing must be false in: {', '.join(wrong)}"


@pytest.mark.parametrize("name", REFRESH_FILES)
def test_refresh_collections_ignore_blank_results(name: str) -> None:
    # PR #16: a week with nothing new made the search fail ("No Items found in Plex") and sent an error
    # notification for every such library each night; ignore_blank_results turns that into a warning.
    collections = load(KOMETA / name)["collections"]  # type: ignore[index]
    assert collections, f"{name} has no collections"
    wrong = [title for title, spec in collections.items() if spec.get("ignore_blank_results") is not True]
    assert not wrong, f"ignore_blank_results must be true in {name}: {', '.join(wrong)}"
