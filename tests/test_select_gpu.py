"""scripts/select-gpu.sh: points compose.host-gpu.yaml, and the Argus agent's `gpu` profile, at the GPU the host has.

Each test runs the script from a copy in a throwaway checkout (with lib.sh beside it, which it sources) against a
fake sysfs tree, with a stand-in for `docker` that records how it was called. The fake `docker info` exits
$FAKE_DOCKER_INFO_EXIT (default 0: Docker answers), the fake `docker compose up` $FAKE_UP_EXIT (default 0). In a
folder named argus-agent (the Argus agent's), the fake records the COMPOSE_PROFILES it got, lists the agent's
services for those profiles (`config --services`: agent, plus plex-exporter and gpu-exporter for the `plex` and `gpu`
profiles) and exits $FAKE_AGENT_CONFIG_EXIT, $FAKE_AGENT_RM_EXIT or $FAKE_AGENT_UP_EXIT; it fails if this stack's
COMPOSE_FILE reaches it.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parent.parent / "scripts"
ROOT = SCRIPTS.parent
BASH = shutil.which("bash") or "/bin/bash"
LINK = "compose.host-gpu.yaml"
UP = "docker compose up --detach --no-deps --wait --wait-timeout 600 plex"

FAKE_DOCKER = """#!/bin/sh
case $PWD in
*/argus-agent)
  if [ -n "${COMPOSE_FILE+set}" ]; then echo "fake docker: the stack's COMPOSE_FILE reached the agent" >&2; exit 3; fi
  printf 'agent: COMPOSE_PROFILES=%s docker %s\\n' "${COMPOSE_PROFILES-unset}" "$*" >> "$FAKE_LOG"
  case "$*" in
  "compose config --services")
    echo agent
    case ,$COMPOSE_PROFILES, in *,plex,*) echo plex-exporter ;; esac
    case ,$COMPOSE_PROFILES, in *,gpu,*) echo gpu-exporter ;; esac
    exit "${FAKE_AGENT_CONFIG_EXIT:-0}"
    ;;
  "compose rm "*) exit "${FAKE_AGENT_RM_EXIT:-0}" ;;
  "compose up "*) exit "${FAKE_AGENT_UP_EXIT:-0}" ;;
  esac
  exit 0
  ;;
esac
printf 'docker %s\\n' "$*" >> "$FAKE_LOG"
case "$1" in
info) exit "${FAKE_DOCKER_INFO_EXIT:-0}" ;;
compose) exit "${FAKE_UP_EXIT:-0}" ;;
esac
exit 0
"""

# The agent's .env as on a host: settings around COMPOSE_PROFILES that must come through a rewrite unchanged.
AGENT_ENV = """ARGUS_HOST=gpu-host
# Password of the Argus server's Prometheus user.
ARGUS_PROMETHEUS_PASSWORD=not-a-real-password
{profiles}HOMELAB_PULL_DIR=/srv/homelab-pull
"""


def agent_config(profiles: str) -> str:
    return f"agent: COMPOSE_PROFILES={profiles} docker compose config --services"


def agent_rm(profiles: str, services: str) -> str:
    return f"agent: COMPOSE_PROFILES={profiles} docker compose rm --stop --force {services}"


def agent_up(profiles: str, services: str) -> str:
    return f"agent: COMPOSE_PROFILES={profiles} docker compose up --detach --wait --wait-timeout 300 {services}"


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

    @property
    def agent_env(self) -> Path:
        """The .env of the Argus agent in its default folder, ~/argus-agent."""
        return self.home / "argus-agent" / ".env"

    def agent(self, line: str | None) -> None:
        """An Argus agent whose .env has the COMPOSE_PROFILES line `line` (None: no such line), at mode 600."""
        self.agent_env.parent.mkdir()
        self.agent_env.write_text(AGENT_ENV.format(profiles="" if line is None else line + "\n"), encoding="utf-8")
        self.agent_env.chmod(0o600)

    def agent_profiles(self) -> list[str]:
        """The agent's COMPOSE_PROFILES lines now."""
        lines = self.agent_env.read_text(encoding="utf-8").splitlines()
        return [line for line in lines if line.startswith("COMPOSE_PROFILES=")]

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
    assert f"{LINK} already points at compose.intel.yaml" in result.stdout
    assert f"No Argus agent in {host.home / 'argus-agent'} (no .env): left alone" in result.stdout
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
    assert "Docker didn't answer within 0s" in result.stderr
    assert "Plex wasn't recreated: once Docker answers, run `docker compose up --detach --wait plex` here" in (
        result.stderr
    )
    assert host.calls() == ["docker info"]


def test_fails_when_plex_doesnt_come_up(host: Host) -> None:
    host.device("0000:01:00.0", INTEL, "i915")
    result = host.run(COMPOSE_FILE=f"compose.yaml:{LINK}", FAKE_UP_EXIT="1")
    assert result.returncode == 1
    assert host.calls() == ["docker info", UP]


# A GPU for the Argus agent tests, as (ids, driver), and the override the link points at for it.
NVIDIA_ON = (NVIDIA, "nvidia")
NVIDIA_VFIO = (NVIDIA, "vfio-pci")
INTEL_ON = (INTEL, "i915")
OVERRIDE = {"nvidia": "compose.gpu.yaml", "i915": "compose.intel.yaml"}


def with_gpu(host: Host, gpu: tuple[tuple[str, str], str] | None) -> None:
    """The host has `gpu` (None: none), and the link already points at its override, so Plex doesn't change."""
    driver = None
    if gpu is not None:
        ids, driver = gpu
        host.device("0000:01:00.0", ids, driver)
    (host.dir / LINK).symlink_to(OVERRIDE.get(driver or "", "compose.cpu.yaml"))


@pytest.mark.parametrize(
    ("gpu", "line", "old", "new"),
    [
        (INTEL_ON, "COMPOSE_PROFILES=plex,gpu", "plex,gpu", "plex"),  # a failover to the Intel GPU
        (INTEL_ON, "COMPOSE_PROFILES=gpu,plex", "gpu,plex", "plex"),
        (INTEL_ON, 'COMPOSE_PROFILES="plex,gpu"', "plex,gpu", "plex"),
        (NVIDIA_VFIO, "COMPOSE_PROFILES=plex,gpu", "plex,gpu", "plex"),  # an NVIDIA GPU without its driver
        (None, "COMPOSE_PROFILES=gpu", "gpu", ""),
        (NVIDIA_ON, "COMPOSE_PROFILES=plex", "plex", "plex,gpu"),  # back on the NVIDIA GPU
        (NVIDIA_ON, "COMPOSE_PROFILES=", "", "gpu"),
        (NVIDIA_ON, None, "", "gpu"),  # no COMPOSE_PROFILES line yet: one is added
    ],
)
def test_the_agents_gpu_profile_follows_the_gpu(
    host: Host, gpu: tuple[tuple[str, str], str] | None, line: str | None, old: str, new: str
) -> None:
    host.agent(line)
    with_gpu(host, gpu)
    # The stack's settings (this COMPOSE_FILE, lib.sh's COMPOSE_PROFILES=tools) don't reach the agent.
    result = host.run(COMPOSE_FILE=f"compose.yaml:{LINK}")
    assert result.returncode == 0, result.stderr
    assert f"Moving the Argus agent from COMPOSE_PROFILES={old} to COMPOSE_PROFILES={new}" in result.stdout
    change = agent_up(new, "gpu-exporter") if "gpu" in new.split(",") else agent_rm(old, "gpu-exporter")
    assert host.calls() == ["docker info", agent_config(old), agent_config(new), change]
    # Only the COMPOSE_PROFILES line changed (or was added at the end), and the file is still private.
    expected = AGENT_ENV.format(profiles=f"COMPOSE_PROFILES={new}\n" if line is not None else "")
    if line is None:
        expected += f"COMPOSE_PROFILES={new}\n"
    assert host.agent_env.read_text(encoding="utf-8") == expected
    assert stat.S_IMODE(host.agent_env.stat().st_mode) == 0o600
    assert not host.agent_env.with_name(".env.new").exists()


@pytest.mark.parametrize(
    ("gpu", "line"),
    [
        (NVIDIA_ON, "COMPOSE_PROFILES=plex,gpu"),
        (NVIDIA_ON, "COMPOSE_PROFILES=gpu,plex"),
        (INTEL_ON, "COMPOSE_PROFILES=plex"),
        (INTEL_ON, "COMPOSE_PROFILES="),
        (None, None),
    ],
)
def test_changes_nothing_when_the_agents_profiles_fit(
    host: Host, gpu: tuple[tuple[str, str], str] | None, line: str | None
) -> None:
    host.agent(line)
    before = host.agent_env.read_text(encoding="utf-8")
    with_gpu(host, gpu)
    result = host.run(COMPOSE_FILE=f"compose.yaml:{LINK}")
    assert result.returncode == 0, result.stderr
    assert "already fits the GPU" in result.stdout
    assert host.calls() == []
    assert host.agent_env.read_text(encoding="utf-8") == before


def test_a_failover_recreates_plex_then_moves_the_agent(host: Host) -> None:
    host.agent("COMPOSE_PROFILES=plex,gpu")
    (host.dir / LINK).symlink_to("compose.gpu.yaml")
    host.device("0000:01:00.0", INTEL, "i915")
    result = host.run(COMPOSE_FILE=f"compose.yaml:{LINK}")
    assert result.returncode == 0, result.stderr
    assert host.link() == "compose.intel.yaml"
    assert host.calls() == [
        "docker info",
        UP,
        agent_config("plex,gpu"),
        agent_config("plex"),
        agent_rm("plex,gpu", "gpu-exporter"),
    ]
    assert host.agent_profiles() == ["COMPOSE_PROFILES=plex"]


def test_moves_the_agent_even_when_plex_doesnt_come_up(host: Host) -> None:
    host.agent("COMPOSE_PROFILES=plex,gpu")
    (host.dir / LINK).symlink_to("compose.gpu.yaml")
    host.device("0000:01:00.0", INTEL, "i915")
    result = host.run(COMPOSE_FILE=f"compose.yaml:{LINK}", FAKE_UP_EXIT="1")
    assert result.returncode == 1
    assert host.calls()[-1] == agent_rm("plex,gpu", "gpu-exporter")
    assert host.agent_profiles() == ["COMPOSE_PROFILES=plex"]


@pytest.mark.parametrize(
    ("gpu", "line", "failure", "after"),
    [
        (INTEL_ON, "COMPOSE_PROFILES=plex,gpu", "FAKE_AGENT_RM_EXIT", "COMPOSE_PROFILES=plex"),
        (NVIDIA_ON, "COMPOSE_PROFILES=plex", "FAKE_AGENT_UP_EXIT", "COMPOSE_PROFILES=plex,gpu"),
        (INTEL_ON, "COMPOSE_PROFILES=plex,gpu", "FAKE_AGENT_CONFIG_EXIT", "COMPOSE_PROFILES=plex"),
    ],
)
def test_keeps_the_agents_profiles_when_its_change_fails(
    host: Host, gpu: tuple[tuple[str, str], str], line: str, failure: str, after: str
) -> None:
    host.agent(line)
    before = host.agent_env.read_text(encoding="utf-8")
    with_gpu(host, gpu)
    result = host.run(**{failure: "1"})
    assert result.returncode == 1
    assert host.agent_env.read_text(encoding="utf-8") == before
    assert not host.agent_env.with_name(".env.new").exists()
    # So the next run tries again.
    retry = host.run()
    assert retry.returncode == 0, retry.stderr
    assert host.agent_profiles() == [after]


def test_leaves_the_agent_as_it_is_when_docker_doesnt_answer(host: Host) -> None:
    host.agent("COMPOSE_PROFILES=plex,gpu")
    before = host.agent_env.read_text(encoding="utf-8")
    with_gpu(host, INTEL_ON)
    result = host.run(FAKE_DOCKER_INFO_EXIT="1", GPU_DOCKER_WAIT="0")
    assert result.returncode == 1
    assert "The Argus agent wasn't changed: run this again once Docker answers" in result.stderr
    assert "Plex wasn't recreated" not in result.stderr
    assert host.calls() == ["docker info"]
    assert host.agent_env.read_text(encoding="utf-8") == before


def test_finds_the_agent_where_gpu_argus_agent_dir_says(host: Host, tmp_path: Path) -> None:
    agent = tmp_path / "opt" / "argus-agent"
    agent.mkdir(parents=True)
    (agent / ".env").write_text("COMPOSE_PROFILES=plex,gpu\n", encoding="utf-8")
    with_gpu(host, INTEL_ON)
    result = host.run(GPU_ARGUS_AGENT_DIR=str(agent))
    assert result.returncode == 0, result.stderr
    assert host.calls()[-1] == agent_rm("plex,gpu", "gpu-exporter")
    assert (agent / ".env").read_text(encoding="utf-8") == "COMPOSE_PROFILES=plex\n"


def test_leaves_the_agent_alone_when_gpu_argus_agent_dir_is_empty(host: Host) -> None:
    host.agent("COMPOSE_PROFILES=plex,gpu")
    before = host.agent_env.read_text(encoding="utf-8")
    with_gpu(host, INTEL_ON)
    result = host.run(GPU_ARGUS_AGENT_DIR="")
    assert result.returncode == 0, result.stderr
    assert "Argus" not in result.stdout
    assert host.calls() == []
    assert host.agent_env.read_text(encoding="utf-8") == before


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
