"""deploy_lock in scripts/lib.sh: backup.sh and restore.sh wait for the pull agent's deploy and block the next one.

The agent (homelab-ops' homelab-pull) holds `flock` on <state dir>/<stack>/lock for each run and skips a run while
the lock is busy. Python's fcntl.flock takes the same kind of lock as flock(1), so it stands in for the agent here.
The tests that lock need flock(1) (util-linux, as on the server and CI's Ubuntu runner) and are skipped without it.
"""

import fcntl
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

LIB = Path(__file__).parent.parent / "scripts" / "lib.sh"
BASH = shutil.which("bash") or "/bin/bash"
needs_flock = pytest.mark.skipif(shutil.which("flock") is None, reason="flock(1) isn't installed")


def run(state: Path, script: str, timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    """Source lib.sh, set the wait, take deploy_lock and run `script` while holding it."""
    program = f'set -euo pipefail; . "{LIB}"; deploy_lock_timeout={timeout}; deploy_lock; {script}'
    # The command is this test's own fixed text; nothing in it comes from outside.
    return subprocess.run(  # noqa: S603
        [BASH, "-c", program],
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(state / "home"), "HOMELAB_PULL_STATE_DIR": str(state)},
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def test_without_the_agent_it_does_nothing(tmp_path: Path) -> None:
    result = run(tmp_path, "echo held")
    assert result.returncode == 0, result.stderr
    assert result.stdout == "held\n"
    assert not (tmp_path / "helios").exists()


def test_follows_xdg_state_home_by_default(tmp_path: Path) -> None:
    program = f'set -euo pipefail; . "{LIB}"; deploy_lock; echo held'
    # The command is this test's own fixed text; nothing in it comes from outside.
    result = subprocess.run(  # noqa: S603
        [BASH, "-c", program],
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(tmp_path), "XDG_STATE_HOME": str(tmp_path / "xdg")},
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "xdg").exists()


@needs_flock
def test_holds_the_agents_lock_until_the_script_exits(tmp_path: Path) -> None:
    (tmp_path / "helios").mkdir()
    # A second open of the lock file can't take it while the script holds it.
    result = run(tmp_path, f'if flock --nonblock "{tmp_path}/helios/lock" true; then echo free; else echo held; fi')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "held"
    assert "Waiting" not in result.stdout
    with (tmp_path / "helios" / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)  # released when the script exited


@needs_flock
def test_waits_for_a_deploy_in_progress(tmp_path: Path) -> None:
    (tmp_path / "helios").mkdir()
    with (tmp_path / "helios" / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        threading.Timer(1, fcntl.flock, (lock, fcntl.LOCK_UN)).start()
        result = run(tmp_path, "echo held", timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["Waiting for a deploy by the pull agent to finish (up to 30 s)", "held"]


@needs_flock
def test_fails_before_stopping_anything_when_the_deploy_takes_too_long(tmp_path: Path) -> None:
    (tmp_path / "helios").mkdir()
    with (tmp_path / "helios" / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        result = run(tmp_path, "echo held", timeout=1)
    assert result.returncode == 1
    assert "held" not in result.stdout
    assert "still holds" in result.stderr
    assert "nothing was stopped" in result.stderr
