"""scripts/post-deploy-check.sh: the pull agent's check after a deploy, Kometa's validation with the real values.

Each test runs the script from a copy in a throwaway git repository (it compares commits there) with stand-ins for
`docker` and `timeout` that record how they were called. The fake `docker compose run` prints $FAKE_KOMETA_OUTPUT
and exits $FAKE_KOMETA_EXIT (default 0); with $FAKE_TIMED_OUT set, the fake `timeout` stops it (exit 124).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "post-deploy-check.sh"
BASH = shutil.which("bash") or "/bin/bash"
GIT = shutil.which("git") or "/usr/bin/git"
RUN = "compose run --rm --no-deps -T --name kometa-post-deploy-check kometa --validate --validate-level full"
REMOVE = "rm -f kometa-post-deploy-check"

COMPOSE = """services:
  plex:
    image: example/plex:1.0@sha256:{plex}

  kometa:
    image: kometateam/kometa:{tag}@sha256:{digest}
    environment:
      KOMETA_TIMES: "{times}"
    volumes:
      - ./kometa/config.yml:/config/config.yml:ro

  # The next service's comment, at the services' indentation.
  quickstart:
    image: kometateam/quickstart:v1@sha256:3
"""

# Kometa's report as v2.5.3 prints it, in its box.
PASSED = """| Connecting to TMDb...                                         |
| ==============================================================|
|  Validation Report (full)                                     |
| ==============================================================|
|  Config: //config/config.yml                                  |
|  Errors (0)                                                   |
| ==============================================================|
|  Result: PASSED                                               |
| ==============================================================|
"""
FAILED = PASSED.replace("Errors (0)", "Errors (1):  TMDb Error: Invalid API key").replace("PASSED", "FAILED")

FAKE_DOCKER = """#!/bin/sh
printf 'docker %s\\n' "$*" >> "$FAKE_LOG"
if [ "$1 $2" = "compose run" ]; then
  [ -z "${FAKE_KOMETA_OUTPUT:-}" ] || cat "$FAKE_KOMETA_OUTPUT"
  exit "${FAKE_KOMETA_EXIT:-0}"
fi
exit 0
"""

# Records its options, then runs the command, unless $FAKE_TIMED_OUT says the time ran out.
FAKE_TIMEOUT = """#!/bin/sh
printf 'timeout %s %s\\n' "$1" "$2" >> "$FAKE_LOG"
[ -z "${FAKE_TIMED_OUT:-}" ] || exit 124
shift 2
exec "$@"
"""


class Repo:
    """A checkout with the script, its history of Kometa changes, and the fake tools."""

    def __init__(self, tmp_path: Path) -> None:
        self.dir = tmp_path / "checkout"
        self.log = tmp_path / "calls.log"
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        for name, text in (("docker", FAKE_DOCKER), ("timeout", FAKE_TIMEOUT)):
            (self.bin / name).write_text(text, encoding="utf-8")
            (self.bin / name).chmod(0o755)
        (self.dir / "scripts").mkdir(parents=True)
        shutil.copy2(SCRIPT, self.dir / "scripts" / SCRIPT.name)
        self.git("init", "--quiet", "-b", "main")
        self.settings = {"plex": "1", "tag": "v2.5.3", "digest": "2", "times": "07:30"}
        self.first = self.commit("First", compose=True, kometa="libraries: {}\n")

    def git(self, *args: str) -> str:
        env = {"PATH": os.environ["PATH"], "HOME": str(self.dir), "GIT_CONFIG_NOSYSTEM": "1"}
        identity = ["-c", "user.name=Test", "-c", "user.email=test@example.com", "-c", "commit.gpgsign=false"]
        # The arguments are this test's own fixed values.
        done = subprocess.run(  # noqa: S603
            [GIT, *identity, *args], cwd=self.dir, env=env, capture_output=True, text=True, check=True
        )
        return done.stdout.strip()

    def commit(self, message: str, *, compose: bool = False, kometa: str | None = None, **settings: str) -> str:
        """Commit a change: settings for compose.yaml, and kometa/config.yml's text; returns the commit."""
        self.settings.update(settings)
        if compose or settings:
            (self.dir / "compose.yaml").write_text(COMPOSE.format(**self.settings), encoding="utf-8")
        if kometa is not None:
            (self.dir / "kometa").mkdir(exist_ok=True)
            (self.dir / "kometa" / "config.yml").write_text(kometa, encoding="utf-8")
        self.git("add", "--all")
        self.git("commit", "--quiet", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")

    def run(self, deployed: str, checked: str = "", **extra: str) -> subprocess.CompletedProcess[str]:
        env = {
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(self.dir),
            "FAKE_LOG": str(self.log),
            "HOMELAB_PULL_DEPLOYED": deployed,
            "HOMELAB_PULL_CHECKED": checked,
            **extra,
        }
        # The script is this repository's own; nothing in the command comes from outside.
        return subprocess.run(  # noqa: S603
            [BASH, str(self.dir / "scripts" / SCRIPT.name)],
            cwd=self.dir.parent,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )

    def output(self, name: str, text: str) -> dict[str, str]:
        """Kometa's output for the fake `docker compose run`."""
        path = self.dir.parent / name
        path.write_text(text, encoding="utf-8")
        return {"FAKE_KOMETA_OUTPUT": str(path)}

    def calls(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    return Repo(tmp_path)


def test_validates_with_the_real_values_when_never_checked(repo: Repo) -> None:
    result = repo.run(repo.first, **repo.output("passed.txt", PASSED))
    assert result.returncode == 0, result.stderr
    assert "No earlier passing check to compare with" in result.stdout
    # A leftover container is removed first; the validation runs in a one-off container, flags as separate words.
    assert repo.calls() == [f"docker {REMOVE}", "timeout --kill-after=20 480", f"docker {RUN}"]
    assert "Validation Report (full)" in result.stdout
    assert "Result: PASSED" in result.stdout
    assert "|" not in result.stdout  # Kometa's box drawing is gone
    assert result.stdout.endswith("Kometa check: passed\n")


@pytest.mark.parametrize(
    ("kometa", "settings", "message"),
    [
        ("libraries: {Movies: {}}\n", {}, "kometa/ changed"),
        (None, {"tag": "v2.5.4", "digest": "9"}, "a Kometa image bump"),
        (None, {"digest": "9"}, "a rebuild of the same tag"),
        (None, {"times": "08:00"}, "another setting of the service"),
    ],
)
def test_validates_when_kometa_changed(repo: Repo, kometa: str | None, settings: dict[str, str], message: str) -> None:
    new = repo.commit(message, kometa=kometa, **settings)
    result = repo.run(new, repo.first, **repo.output("passed.txt", PASSED))
    assert result.returncode == 0, result.stderr
    assert f"Kometa changed since {repo.first[:7]}" in result.stdout
    assert f"docker {RUN}" in repo.calls()


@pytest.mark.parametrize(
    "change",
    [
        {"plex": "9"},  # another service's image
        {},  # nothing in compose.yaml or kometa/ (docs, CI)
    ],
)
def test_passes_at_once_when_kometa_is_unchanged(repo: Repo, change: dict[str, str]) -> None:
    new = repo.commit("Unrelated", **change)
    result = repo.run(new, repo.first)
    assert result.returncode == 0, result.stderr
    assert f"Kometa hasn't changed since {repo.first[:7]}, where this check last passed" in result.stdout
    assert repo.calls() == []


def test_the_next_services_comment_is_not_kometas(repo: Repo) -> None:
    text = (repo.dir / "compose.yaml").read_text(encoding="utf-8")
    (repo.dir / "compose.yaml").write_text(text.replace("next service's comment", "next comment"), encoding="utf-8")
    new = repo.commit("Reword a comment")
    assert repo.run(new, repo.first).returncode == 0
    assert repo.calls() == []


def test_validates_when_the_last_passing_commit_is_unknown(repo: Repo) -> None:
    result = repo.run(repo.first, "0" * 40, **repo.output("passed.txt", PASSED))
    assert result.returncode == 0, result.stderr
    assert "No earlier passing check to compare with" in result.stdout
    assert f"docker {RUN}" in repo.calls()


def test_failed_validation_fails_with_kometas_report(repo: Repo) -> None:
    result = repo.run(repo.first, FAKE_KOMETA_EXIT="1", **repo.output("failed.txt", FAILED))
    assert result.returncode == 1
    assert "TMDb Error: Invalid API key" in result.stdout
    assert "Result: FAILED" in result.stdout
    assert "Kometa check: failed: docker compose run (Kometa) exited 1" in result.stderr
    assert "logs/meta.log" in result.stderr


def test_failed_result_fails_even_with_exit_0(repo: Repo) -> None:
    result = repo.run(repo.first, **repo.output("failed.txt", FAILED))
    assert result.returncode == 1
    assert "Kometa check: failed: Result: FAILED" in result.stderr


def test_no_result_fails(repo: Repo) -> None:
    """Without network Kometa gives up, exits 0 and prints no result: its last lines are shown instead."""
    result = repo.run(repo.first, **repo.output("offline.txt", "| Connecting to TMDb...\n| retrying\n"))
    assert result.returncode == 1
    assert "Kometa's last lines:" in result.stdout
    assert "retrying" in result.stdout
    assert "Kometa printed no result (it needs network to validate)" in result.stderr


def test_a_validation_that_runs_too_long_is_stopped_and_removed(repo: Repo) -> None:
    result = repo.run(repo.first, FAKE_TIMED_OUT="1", KOMETA_CHECK_TIMEOUT="5")
    assert result.returncode == 1
    assert repo.calls() == [f"docker {REMOVE}", "timeout --kill-after=20 5", f"docker {REMOVE}"]
    assert "didn't finish within 5s (KOMETA_CHECK_TIMEOUT)" in result.stderr


@pytest.mark.parametrize("value", ["soon", "-1", "1.5"])
def test_rejects_a_bad_timeout(repo: Repo, value: str) -> None:
    result = repo.run(repo.first, KOMETA_CHECK_TIMEOUT=value)
    assert result.returncode == 2
    assert "KOMETA_CHECK_TIMEOUT must be a number of seconds" in result.stderr
    assert repo.calls() == []


def test_needs_the_deployed_commit(repo: Repo) -> None:
    result = repo.run("")
    assert result.returncode != 0
    assert "the commit deployed" in result.stderr
    assert repo.calls() == []
