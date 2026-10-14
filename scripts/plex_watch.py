"""Watch linuxserver.io's Plex builds weekly: is there a newer Plex version or image build than compose.yaml's pin.

Dependabot can't follow Plex: every tag of linuxserver.io's Plex image carries Plex's commit hash
(1.43.4.10903-e5521bd8c-ls327), which none of Dependabot's tag patterns read, so it never proposes an update
(docs/dependencies.md). This watch does instead. It compares the Plex image pinned in compose.yaml with the newest
published build of linuxserver/docker-plex (one GitHub release per build) and, while they differ, keeps one issue,
"Plex update available", up to date with the newer builds (a new Plex version or a rebuild of the same one with
newer base packages) and the latest one's image digest, ready to pin by hand.

The issue's state (pinned and latest tag, latest digest) is kept in a hidden HTML comment at the end of its body. A
run whose state matches the open issue's changes nothing: no edit, no comment, no alert. A new state rewrites the
body, adds one comment and sends the optional alert (NTFY_URL, DISCORD_WEBHOOK). Once the pin is the latest build,
the issue is closed; when they diverge again it is reopened, never duplicated.

Usage: scripts/plex_watch.py [--dry-run] [--pinned IMAGE] [--repo OWNER/NAME]
Environment: GITHUB_REPOSITORY, GH_TOKEN or GITHUB_TOKEN, NTFY_URL, DISCORD_WEBHOOK (all optional for --dry-run).
Exit codes: 0 = done (whatever the findings), 1 = it couldn't check (GitHub, Docker or compose.yaml failed).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from kometa_watch import GitHub, WatchError, image_digest, post

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "compose.yaml"
UPSTREAM = "linuxserver/docker-plex"
IMAGE = "lscr.io/linuxserver/plex"
DEFAULT_REPO = "HoneyBearTech/homelab-helios"
TITLE = "Plex update available"
BOT = "github-actions[bot]"
MARKER = "plex-update-watch"
STATE = re.compile(r"<!-- " + MARKER + r" (\{[^<>]*\}) -->")
# Plex's version (four numbers and its commit hash) and linuxserver.io's build number.
TAG = re.compile(r"^(\d+)\.(\d+)\.(\d+)\.(\d+)-([0-9a-f]+)-ls(\d+)$")
PIN = re.compile(r"^\s*image:\s*(" + re.escape(IMAGE) + r":\S+@sha256:[0-9a-f]{64})\s*$", re.MULTILINE)
PER_PAGE = 100


@dataclass(frozen=True)
class Build:
    """A published linuxserver.io build of Plex."""

    tag: str
    url: str
    published: str

    @property
    def plex_version(self) -> str:
        """Return Plex's own version, without linuxserver.io's build number."""
        return self.tag.rsplit("-ls", 1)[0]


@dataclass
class Findings:
    """What one run found; the issue body and its state are made from this."""

    pinned: str  # image pinned in compose.yaml: lscr.io/linuxserver/plex:<tag>@sha256:...
    latest: str  # newest build's tag
    digest: str  # newest build's image digest
    newer: list[Build]

    @property
    def pinned_tag(self) -> str:
        """Return the pinned image's tag."""
        return split_image(self.pinned)[1]

    @property
    def in_step(self) -> bool:
        """Tell whether the pin is the newest build, with its current digest."""
        _, tag, digest = split_image(self.pinned)
        return tag == self.latest and digest == self.digest

    def state(self) -> dict[str, str]:
        """Return what a reader of the issue wants to hear about when it changes."""
        return {"pinned": self.pinned_tag, "latest": self.latest, "digest": self.digest}

    def summary(self) -> str:
        """Return one line for the issue comment and the alert."""
        pinned = sort_key(self.pinned_tag)
        latest = sort_key(self.latest)
        kind = "a new Plex version" if pinned and latest and pinned[:4] != latest[:4] else "a rebuild"
        if self.in_step:
            return f"compose.yaml pins {self.latest}, the newest Plex image."
        if self.latest == self.pinned_tag:
            kind = "a new digest for the pinned build"
        return f"newest Plex image {self.latest} (pinned: {self.pinned_tag}): {kind}."


def split_image(image: str) -> tuple[str, str, str]:
    """Split name:tag@digest into (name, tag, digest)."""
    ref, _, digest = image.partition("@")
    name, _, tag = ref.rpartition(":")
    if not (name and TAG.match(tag) and digest.startswith("sha256:")):
        message = f"not a Plex name:<version>-<hash>-lsN@sha256:... image: {image}"
        raise WatchError(message)
    return name, tag, digest


def sort_key(tag: str) -> tuple[int, ...] | None:
    """Return (the four parts of Plex's version, the build number) of a build tag, or None."""
    match = TAG.match(tag)
    if not match:
        return None
    numbers = match.groups()
    return (*(int(part) for part in numbers[:4]), int(numbers[5]))


def builds_after(raw: list[dict[str, Any]], pinned: str) -> list[Build]:
    """Return the published (not draft or pre-release) builds newer than the pinned tag, oldest first."""
    floor = sort_key(pinned)
    found = []
    for release in raw:
        tag = str(release.get("tag_name", ""))
        key = sort_key(tag)
        if key is None or release.get("draft") or release.get("prerelease"):
            continue
        if floor is None or key > floor:
            build = Build(tag, str(release.get("html_url", "")), str(release.get("published_at") or "")[:10])
            found.append((key, build))
    return [build for _, build in sorted(found)]


def pinned_image(compose: Path = COMPOSE) -> str:
    """Return the Plex image pinned in compose.yaml."""
    matches = PIN.findall(compose.read_text(encoding="utf-8"))
    if len(matches) != 1:
        message = f"expected one {IMAGE} image in {compose.name}, found {len(matches)}"
        raise WatchError(message)
    return matches[0]


def parse_state(body: str | None) -> dict[str, str] | None:
    """Return the state in an issue body: the last marker comment (ours is always the last one)."""
    matches = STATE.findall(body or "")
    if not matches:
        return None
    try:
        state = json.loads(matches[-1])
    except ValueError:
        return None
    return state if isinstance(state, dict) else None


def decide(*, in_step: bool, issue: dict[str, Any] | None, state: dict[str, str]) -> str:
    """Choose what to do with the issue: nothing, create, update, reopen or close."""
    if in_step:
        return "close" if issue and issue.get("state") == "open" else "nothing"
    if issue is None:
        return "create"
    if issue.get("state") != "open":
        return "reopen"
    return "nothing" if parse_state(issue.get("body")) == state else "update"


def render(findings: Findings) -> str:
    """Return the issue body, ending with the state comment."""
    name, pinned_tag, pinned_digest = split_image(findings.pinned)
    lines = [
        (
            "linuxserver.io's Plex builds compared with `compose.yaml` by the weekly watch (`scripts/plex_watch.py`). "
            "Dependabot can't follow Plex's tags, so this update is made by hand: pin the latest build's tag and "
            "digest below in a pull request, then deploy as in `docs/upgrading.md`."
        ),
        "",
        "| | Tag | Image digest |",
        "| --- | --- | --- |",
        f"| Pinned (`{name}`) | {pinned_tag} | `{pinned_digest}` |",
        f"| Latest build | {findings.latest} | `{findings.digest}` |",
        "",
    ]
    if findings.newer:
        lines.append("Newer builds:")
        lines += [f"- [{b.tag}]({b.url}) ({b.published}, Plex {b.plex_version})" for b in findings.newer]
    elif findings.in_step:
        lines.append("No newer build: the pin is the newest one.")
    else:
        lines.append(f"No newer build, but {findings.latest}'s image now has another digest.")
    lines += ["", f"`image: {IMAGE}:{findings.latest}@{findings.digest}`", "", state_comment(findings.state())]
    return "\n".join(lines)


def state_comment(state: dict[str, str]) -> str:
    """Return the hidden comment that carries the state."""
    return f"<!-- {MARKER} {json.dumps(state, sort_keys=True)} -->"


def find_issue(github: GitHub, repo: str) -> dict[str, Any] | None:
    """Return our issue: the open one, else the most recent closed one."""
    issues = github.items(f"/repos/{repo}/issues?state=all&creator={quote(BOT)}&per_page={PER_PAGE}")
    ours = [
        issue
        for issue in issues
        if "pull_request" not in issue and issue.get("title") == TITLE and parse_state(issue.get("body")) is not None
    ]
    if not ours:
        return None
    open_issues = [issue for issue in ours if issue.get("state") == "open"]
    return (open_issues or sorted(ours, key=lambda issue: int(issue.get("number", 0))))[-1]


def apply(github: GitHub, repo: str, action: str, issue: dict[str, Any] | None, findings: Findings) -> str:
    """Carry out the action on GitHub; return the issue's URL."""
    if action == "create":
        created = github.call("POST", f"/repos/{repo}/issues", {"title": TITLE, "body": render(findings)})
        return str(created.get("html_url", "")) if isinstance(created, dict) else ""
    if issue is None:
        return ""
    path = f"/repos/{repo}/issues/{issue['number']}"
    if action in {"update", "reopen"}:
        github.call("PATCH", path, {"body": render(findings), "state": "open"})
        verb = "Updated" if action == "update" else "Reopened"
        github.call("POST", f"{path}/comments", {"body": f"{verb}: {findings.summary()}"})
    elif action == "close":
        github.call(
            "POST",
            f"{path}/comments",
            {"body": f"Back in step: compose.yaml pins {findings.latest}, the newest build."},
        )
        github.call("PATCH", path, {"state": "closed", "state_reason": "completed"})
    return str(issue.get("html_url", ""))


def notify(text: str, env: dict[str, str]) -> list[str]:
    """Send the short alert to whichever of NTFY_URL and DISCORD_WEBHOOK is set; return the ones sent."""
    targets = {
        "ntfy": (env.get("NTFY_URL", ""), text.encode(), {"Title": TITLE, "Content-Type": "text/plain"}),
        "discord": (
            env.get("DISCORD_WEBHOOK", ""),
            json.dumps({"content": text}).encode(),
            {"Content-Type": "application/json"},
        ),
    }
    sent = []
    for name, (url, data, headers) in targets.items():
        if not url:
            continue
        if not url.startswith("https://"):
            print(f"::warning::{name}: not an https URL, no alert sent")
            continue
        try:
            post(url, data, headers)
        except (urllib.error.URLError, OSError) as error:
            print(f"::warning::{name}: the alert failed ({error})")
            continue
        sent.append(name)
    return sent


def gather(github: GitHub, pinned: str) -> Findings:
    """Compare the pinned image with linuxserver.io's newest Plex build."""
    name, tag, _ = split_image(pinned)
    newer = builds_after(github.items(f"/repos/{UPSTREAM}/releases?per_page={PER_PAGE}"), tag)
    latest = newer[-1].tag if newer else tag
    return Findings(pinned, latest, image_digest(name, latest), newer)


def main(argv: list[str] | None = None) -> int:
    """Run the watch."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="print the action and the issue body; change nothing")
    parser.add_argument("--pinned", help="pretend this image is pinned (lscr.io/linuxserver/plex:<tag>@sha256:...)")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY") or DEFAULT_REPO, help="OWNER/NAME")
    args = parser.parse_args(argv)
    github = GitHub(os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))
    try:
        findings = gather(github, args.pinned or pinned_image())
        issue = find_issue(github, args.repo)
        action = decide(in_step=findings.in_step, issue=issue, state=findings.state())
        if args.dry_run:
            print(f"Action: {action} ({findings.summary()})\n")
            print(render(findings))
            return 0
        url = apply(github, args.repo, action, issue, findings)
    except WatchError as error:
        print(f"::error::{error}")
        return 1
    print(f"{action}: {url or 'no issue'} ({findings.summary()})")
    if action in {"create", "update", "reopen"}:
        sent = notify(f"Plex: {findings.summary()} {url}", dict(os.environ))
        print(f"Alerts sent: {', '.join(sent) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
