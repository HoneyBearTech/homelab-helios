"""scripts/select-gpu.sh: points compose.host-gpu.yaml at the override for the GPU the host has, at boot.

Each test runs the script from a copy in a throwaway checkout (with lib.sh beside it, which it sources) against a
fake sysfs tree, with a stand-in for `docker` that records how it was called. The fake `docker info` exits
$FAKE_DOCKER_INFO_EXIT (default 0: Docker answers), the fake `docker compose up` $FAKE_UP_EXIT (default 0).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parent.parent / "scripts"
ROOT = SCRIPTS.parent
BASH = shutil.which("bash") or "/bin/bash"
LINK = "compose.host-gpu.yaml"
UP = "docker compose up --detach --no-deps --wait --wait-timeout 600 plex"

FAKE_DOCKER = """#!/bin/sh
printf 'docker %s\\n' "$*" >> "$FAKE_LOG"
case "$1" in
info) exit "${FAKE_DOCKER_INFO_EXIT:-0}" ;;
compose) exit "${FAKE_UP_EXIT:-0}" ;;
esac
exit 0
"""

NVIDIA = ("0x10de", "0x030000")
INTEL = ("0x8086", "0x030000")


class Host:
    """A checkout with the script, a fake sysfs and a fake docker."""

    def __init__(self, tmp_path: Path) -> None:
        self.dir = tmp_path / "checkout"
        self.sys = tmp_path / "sys"
        self.log = tmp_path / "calls.log"
        self.bin = tmp_path / "bin"
        self.home = tmp_path / "home"
        for path in (self.dir / "scripts", self.sys / "bus" / "pci" / "devices", self.bin, self.home):
            path.mkdir(parents=True)
        for name in ("select-gpu.sh", "lib.sh"):
            shutil.copy2(SCRIPTS / name, self.dir / "scripts" / name)
        (self.bin / "docker").write_text(FAKE_DOCKER, encoding="utf-8")
        (self.bin / "docker").chmod(0o755)

    def device(self, address: str, ids: tuple[str, str], driver: str | None, *, render: bool = True) -> None:
        """A PCI device: (vendor, class), the driver bound to it (None: none) and, for a GPU, its DRM nodes."""
        path = self.sys / "bus" / "pci" / "devices" / address
        (path / "drm" / "card1").mkdir(parents=True)
        if render:
            (path / "drm" / "renderD128").mkdir()
        vendor, pci_class = ids
        (path / "vendor").write_text(vendor + "\n", encoding="utf-8")
        (path / "class").write_text(pci_class + "\n", encoding="utf-8")
        if driver:
            target = self.sys / "bus" / "pci" / "drivers" / driver
            target.mkdir(parents=True, exist_ok=True)
            (path / "driver").symlink_to(target)

    def env_file(self, text: str) -> None:
        (self.dir / ".env").write_text(text, encoding="utf-8")

    def link(self) -> str | None:
        path = self.dir / LINK
        return str(path.readlink()) if path.is_symlink() else None

    def run(self, **extra: str) -> subprocess.CompletedProcess[str]:
        env = {
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(self.home),
            "XDG_STATE_HOME": str(self.home / "state"),  # no pull agent here: deploy_lock does nothing
            "FAKE_LOG": str(self.log),
            "GPU_SYSFS": str(self.sys),
            **extra,
        }
        # The script is this repository's own; nothing in the command comes from outside.
        return subprocess.run(  # noqa: S603
            [BASH, str(self.dir / "scripts" / "select-gpu.sh")],
            cwd=self.dir.parent,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )

    def calls(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []


@pytest.fixture
def host(tmp_path: Path) -> Host:
    return Host(tmp_path)


@pytest.mark.parametrize(
    ("devices", "target"),
    [
        ([("0000:01:00.0", NVIDIA, "nvidia")], "compose.gpu.yaml"),
        ([("0000:01:00.0", INTEL, "i915")], "compose.intel.yaml"),
        ([("0000:01:00.0", INTEL, "xe")], "compose.intel.yaml"),
        ([("0000:01:00.0", ("0x8086", "0x038000"), "i915")], "compose.intel.yaml"),  # "display controller" class
        ([("0000:00:02.0", INTEL, "i915"), ("0000:01:00.0", NVIDIA, "nvidia")], "compose.gpu.yaml"),  # NVIDIA wins
        ([("0000:00:01.0", ("0x1234", "0x030000"), "bochs-drm")], "compose.cpu.yaml"),  # the VM's own display
        ([("0000:00:19.0", ("0x8086", "0x020000"), "e1000e")], "compose.cpu.yaml"),  # an Intel NIC isn't a GPU
        ([], "compose.cpu.yaml"),
    ],
)
def test_points_the_link_at_the_gpu_found(
    host: Host, devices: list[tuple[str, tuple[str, str], str]], target: str
) -> None:
    for address, ids, driver in devices:
        host.device(address, ids, driver)
    result = host.run(COMPOSE_FILE="compose.yaml")
    assert result.returncode == 0, result.stderr
    assert host.link() == target
    assert f"-> {target}" in result.stdout
    assert not (host.dir / f"{LINK}.new").exists()


@pytest.mark.parametrize(
    ("ids", "driver", "shown"),
    [
        (NVIDIA, "vfio-pci", "vfio-pci"),  # still handed to a VM on this host
        (NVIDIA, None, "no driver"),  # the driver didn't load (a kernel update without its DKMS build)
        (INTEL, "vfio-pci", "vfio-pci"),
    ],
)
def test_a_gpu_without_its_driver_isnt_used(host: Host, ids: tuple[str, str], driver: str | None, shown: str) -> None:
    host.device("0000:01:00.0", ids, driver)
    result = host.run(COMPOSE_FILE="compose.yaml")
    assert result.returncode == 0, result.stderr
    assert host.link() == "compose.cpu.yaml"
    assert f"Not usable (wrong or no driver): 0000:01:00.0 ({shown})" in result.stdout


def test_an_intel_gpu_without_a_render_node_isnt_used(host: Host) -> None:
    host.device("0000:01:00.0", INTEL, "i915", render=False)
    assert host.run(COMPOSE_FILE="compose.yaml").returncode == 0
    assert host.link() == "compose.cpu.yaml"


@pytest.mark.parametrize(
    ("env", "env_file"),
    [
        ({"COMPOSE_FILE": f"compose.yaml:{LINK}"}, None),
        ({}, f"TZ=Etc/UTC\nCOMPOSE_FILE=compose.yaml:{LINK}\n"),
        ({}, f'COMPOSE_FILE="compose.yaml:{LINK}"\n'),
    ],
)
def test_recreates_plex_when_the_link_changes(host: Host, env: dict[str, str], env_file: str | None) -> None:
    if env_file is not None:
        host.env_file(env_file)
    (host.dir / LINK).symlink_to("compose.gpu.yaml")
    host.device("0000:01:00.0", INTEL, "i915")
    result = host.run(**env)
    assert result.returncode == 0, result.stderr
    assert host.link() == "compose.intel.yaml"
    assert "now points at compose.intel.yaml (was compose.gpu.yaml)" in result.stdout
    assert host.calls() == ["docker info", UP]


def test_changes_nothing_when_the_link_is_right(host: Host) -> None:
    (host.dir / LINK).symlink_to("compose.intel.yaml")
    host.device("0000:01:00.0", INTEL, "i915")
    result = host.run(COMPOSE_FILE=f"compose.yaml:{LINK}")
    assert result.returncode == 0, result.stderr
    assert f"{LINK} already points at compose.intel.yaml: nothing to change" in result.stdout
    assert host.calls() == []


@pytest.mark.parametrize("env_file", [None, "COMPOSE_FILE=compose.yaml:compose.gpu.yaml\n"])
def test_leaves_plex_alone_when_compose_file_doesnt_name_the_link(host: Host, env_file: str | None) -> None:
    if env_file is not None:
        host.env_file(env_file)
    host.device("0000:01:00.0", INTEL, "i915")
    result = host.run()
    assert result.returncode == 0, result.stderr
    assert host.link() == "compose.intel.yaml"  # kept current all the same
    assert f"doesn't name {LINK}, so the stack doesn't follow it" in result.stdout
    assert host.calls() == []


def test_fails_when_docker_doesnt_answer(host: Host) -> None:
    host.device("0000:01:00.0", INTEL, "i915")
    result = host.run(COMPOSE_FILE=f"compose.yaml:{LINK}", FAKE_DOCKER_INFO_EXIT="1", GPU_DOCKER_WAIT="0")
    assert result.returncode == 1
    assert "Docker didn't answer within 0s; Plex wasn't recreated" in result.stderr
    assert host.calls() == ["docker info"]


def test_fails_when_plex_doesnt_come_up(host: Host) -> None:
    host.device("0000:01:00.0", INTEL, "i915")
    result = host.run(COMPOSE_FILE=f"compose.yaml:{LINK}", FAKE_UP_EXIT="1")
    assert result.returncode == 1
    assert host.calls() == ["docker info", UP]


@pytest.mark.parametrize("value", ["soon", "-5", "1.5"])
def test_rejects_a_wait_that_isnt_a_number(host: Host, value: str) -> None:
    result = host.run(GPU_DOCKER_WAIT=value)
    assert result.returncode == 2
    assert "GPU_DOCKER_WAIT must be a number of seconds" in result.stderr


def test_every_target_is_a_committed_override() -> None:
    script = (SCRIPTS / "select-gpu.sh").read_text(encoding="utf-8")
    for name in ("compose.gpu.yaml", "compose.intel.yaml", "compose.cpu.yaml"):
        assert f"target={name}" in script
        assert (ROOT / name).is_file()
    assert LINK in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
