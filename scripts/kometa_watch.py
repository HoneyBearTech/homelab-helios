"""Watch Kometa's releases weekly: does kometa/ still validate, and what changed upstream that we use.

Compares the Kometa image pinned in compose.yaml with Kometa's latest release. While they differ, or kometa/ doesn't
validate against the latest release, it keeps one issue, "Kometa upstream changes", up to date with:

- the newer releases, and the latest one's tag and image digest;
- the validation of kometa/ against the latest release and its JSON schemas (scripts/kometa-validate.sh);
- the release-note bullets that name a key, builder or default our files use, or that deprecate, remove or rename
  something;
- the diff of the defaults/ files our configuration references, between the pinned tag and the latest.

The issue's state (pinned and latest tag, latest digest, hashes of the validation report and of the diff) is kept
in a hidden HTML comment at the end of its body. A run whose state matches the open issue's changes nothing: no
edit, no comment, no alert. A new state rewrites the body, adds one comment and sends the optional alert (NTFY_URL,
DISCORD_WEBHOOK). Once the pin is the latest release and kometa/ validates against it, the issue is closed; when
they diverge again it is reopened, never duplicated.

Usage: scripts/kometa_watch.py [--dry-run] [--pinned IMAGE] [--existing-body FILE] [--repo OWNER/NAME]
Environment: GITHUB_REPOSITORY, GH_TOKEN or GITHUB_TOKEN, NTFY_URL, DISCORD_WEBHOOK (all optional for --dry-run).
Exit codes: 0 = done (whatever the findings), 1 = it couldn't check (GitHub, Docker or the validation failed to run).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
VALIDATE = ROOT / "scripts" / "kometa-validate.sh"
UPSTREAM = "Kometa-Team/Kometa"
API = "https://api.github.com"
DEFAULT_REPO = "HoneyBearTech/homelab-helios"
TITLE = "Kometa upstream changes"
BOT = "github-actions[bot]"
MARKER = "kometa-upstream-watch"
STATE = re.compile(r"<!-- " + MARKER + r" (\{[^<>]*\}) -->")
TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
NOTABLE = re.compile(r"deprecat|remov|renam|breaking", re.IGNORECASE)
KEY = re.compile(r"^\s*(?:-\s+)?([A-Za-z_][A-Za-z0-9_.]*):", re.MULTILINE)
DEFAULT = re.compile(r"^\s*(?:-\s+)?default:\s*([A-Za-z0-9_]+)\s*$", re.MULTILINE)
# Keys too common in Kometa's release notes to point at our configuration; a word also needs 4+ characters.
COMMON = frozenset({
    "all", "apikey", "cache", "changes", "collection", "collections", "config", "configured", "data", "default",
    "ending", "error", "file", "files", "language", "libraries", "library", "managed", "metadata", "name",
    "operations", "overlay", "overlays", "plex", "schedule", "search", "settings", "starting", "tag", "template",
    "templates", "token", "url", "version",
})  # fmt: skip
MIN_WORD = 4
PER_PAGE = 100
MAX_PAGES = 30
MAX_PATCH = 6000  # characters of one file's diff in the issue
MAX_BODY = 60000  # GitHub's limit for an issue body is 65536
TIMEOUT = 30
VALIDATION_FAILED = 1  # kometa-validate.sh: 0 = passed, 1 = failed, anything else = it couldn't run


class WatchError(Exception):
    """Something needed for the check failed (GitHub's API, Docker, the validation script)."""


@dataclass(frozen=True)
class Release:
    """A published Kometa release."""

    tag: str
    url: str
    body: str


@dataclass
class Findings:
    """What one run found; the issue body and its state are made from this."""

    pinned: str  # image pinned in compose.yaml: name:vX.Y.Z@sha256:...
    latest: str  # latest release's tag
    digest: str  # latest release's image digest
    newer: list[Release]
    passed: bool
    report: str
    excerpts: list[tuple[Release, list[str]]] = field(default_factory=list)
    patches: list[tuple[str, str]] = field(default_factory=list)

    @property
    def pinned_tag(self) -> str:
        """Return the pinned image's tag."""
        return split_image(self.pinned)[1]

    @property
    def in_step(self) -> bool:
        """Tell whether the pin is the latest release, with its current digest, and kometa/ validates against it."""
        _, tag, digest = split_image(self.pinned)
        return tag == self.latest and digest == self.digest and self.passed

    def state(self) -> dict[str, str]:
        """Return what a reader of the issue wants to hear about when it changes."""
        diff = "\n".join(f"{path}\n{patch}" for path, patch in self.patches)
        return {
            "pinned": self.pinned_tag,
            "latest": self.latest,
            "digest": self.digest,
            "report": sha256(self.report),
            "diff": sha256(diff),
        }

    def summary(self) -> str:
        """Return one line for the issue comment and the alert."""
        result = "validates" if self.passed else "does NOT validate"
        return (
            f"latest Kometa release {self.latest} (pinned: {self.pinned_tag}); kometa/ {result} against it; "
            f"{len(self.patches)} default file(s) we use changed."
        )


def sha256(text: str) -> str:
    """Return the hex SHA-256 of text."""
    return hashlib.sha256(text.encode()).hexdigest()


def split_image(image: str) -> tuple[str, str, str]:
    """Split name:tag@digest into (name, tag, digest)."""
    ref, _, digest = image.partition("@")
    name, _, tag = ref.rpartition(":")
    if not (name and TAG.match(tag) and digest.startswith("sha256:")):
        message = f"not a name:vX.Y.Z@sha256:... image: {image}"
        raise WatchError(message)
    return name, tag, digest


def version(tag: str) -> tuple[int, ...] | None:
    """Return (major, minor, patch) of a vX.Y.Z tag, or None."""
    match = TAG.match(tag)
    return tuple(int(part) for part in match.groups()) if match else None


def releases_after(raw: list[dict[str, Any]], pinned: str) -> list[Release]:
    """Return the published (not draft or pre-release) vX.Y.Z releases newer than the pinned tag, oldest first."""
    floor = version(pinned)
    found = []
    for release in raw:
        tag = str(release.get("tag_name", ""))
        current = version(tag)
        if current is None or release.get("draft") or release.get("prerelease"):
            continue
        if floor is None or current > floor:
            found.append((current, Release(tag, str(release.get("html_url", "")), str(release.get("body") or ""))))
    return [release for _, release in sorted(found)]


def words_in(texts: list[str]) -> set[str]:
    """Return the keys and default names our files use that are specific enough to look for in release notes."""
    words: set[str] = set()
    for text in texts:
        words.update(KEY.findall(text))
        words.update(DEFAULT.findall(text))
    return {word for word in words if len(word) >= MIN_WORD and word.lower() not in COMMON}


def default_names(texts: list[str]) -> set[str]:
    """Return the names of the Kometa defaults our files reference (`default: <name>`)."""
    return {name for text in texts for name in DEFAULT.findall(text)}


def sanitize(text: str) -> str:
    """Defuse HTML comments in untrusted text (release notes, diffs), so it can't fake the issue's state."""
    return text.replace("<!--", "<!- -").replace("-->", "- ->")


def note_excerpts(releases: list[Release], words: set[str]) -> list[tuple[Release, list[str]]]:
    """Return, per release, the bullets that name one of our words or deprecate, remove or rename something."""
    pattern = None
    if words:
        alternatives = "|".join(re.escape(word) for word in sorted(words, key=len, reverse=True))
        pattern = re.compile(rf"(?<![A-Za-z0-9_])({alternatives})(?![A-Za-z0-9_])", re.IGNORECASE)
    excerpts = []
    for release in releases:
        lines = []
        for line in release.body.splitlines():
            text = line.strip()
            if not text.startswith(("- ", "* ")):
                continue
            hits = sorted({hit.lower() for hit in pattern.findall(text)}) if pattern else []
            if hits or NOTABLE.search(text):
                lines.append(sanitize(text) + (f" _(ours: {', '.join(hits)})_" if hits else ""))
        if lines:
            excerpts.append((release, lines))
    return excerpts


def defaults_patches(files: list[dict[str, Any]], names: set[str]) -> list[tuple[str, str]]:
    """Return (path, diff) of each changed defaults/<...>/<name>.yml whose name our configuration references."""
    patches = []
    for changed in files:
        path = Path(str(changed.get("filename", "")))
        if path.parts[:1] == ("defaults",) and path.suffix == ".yml" and path.stem in names:
            patch = str(changed.get("patch") or "(no diff shown: too large; see the comparison link)")
            patches.append((str(path), patch))
    return sorted(patches)


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
    pinned_name, pinned_tag, pinned_digest = split_image(findings.pinned)
    lines = [
        (
            "Kometa upstream compared with `compose.yaml` by the weekly watch (`scripts/kometa_watch.py`). "
            "Dependabot proposes the update itself; merge it once the `Kometa config` check passes, then deploy "
            "as in `docs/upgrading.md`."
        ),
        "",
        "| | Tag | Image digest |",
        "| --- | --- | --- |",
        f"| Pinned (`{pinned_name}`) | {pinned_tag} | `{pinned_digest}` |",
        f"| Latest release | {findings.latest} | `{findings.digest}` |",
        "",
    ]
    if findings.newer:
        lines.append("Newer releases: " + ", ".join(f"[{r.tag}]({r.url})" for r in findings.newer) + ".")
    elif pinned_digest != findings.digest:
        lines.append(f"No newer release, but {findings.latest}'s image now has another digest.")
    else:
        lines.append("No newer release.")
    result = "passed" if findings.passed else "failed"
    lines += ["", f"### `kometa/` against {findings.latest}: {result}", "", "```text", findings.report, "```", ""]
    lines += ["### Release notes that touch our configuration", ""]
    if findings.excerpts:
        for release, bullets in findings.excerpts:
            lines += [f"**[{release.tag}]({release.url})**", "", *bullets, ""]
    else:
        lines += ["No release-note bullet names a key, builder or default we use.", ""]
    lines += [f"### Defaults we use that changed ({pinned_tag}...{findings.latest})", ""]
    head = "\n".join(lines) + "\n"
    return head + render_patches(findings, budget=MAX_BODY - len(head)) + "\n" + state_comment(findings.state())


def render_patches(findings: Findings, *, budget: int) -> str:
    """Return the changed defaults as collapsed diffs, within budget characters."""
    if not findings.patches:
        return "None of the `defaults/` files our configuration references changed.\n"
    compare = f"https://github.com/{UPSTREAM}/compare/{findings.pinned_tag}...{findings.latest}"
    parts = []
    for path, patch in findings.patches:
        shown = patch if len(patch) <= MAX_PATCH else patch[:MAX_PATCH] + "\n... (cut; see the comparison)"
        part = f"<details><summary><code>{path}</code></summary>\n\n```diff\n{sanitize(shown)}\n```\n</details>\n"
        if len(part) > budget - 500:
            parts.append(f"... and more: [the full comparison]({compare}).\n")
            break
        parts.append(part)
        budget -= len(part)
    return "".join(parts) + f"\n[Full comparison]({compare})\n"


def state_comment(state: dict[str, str]) -> str:
    """Return the hidden comment that carries the state."""
    return f"<!-- {MARKER} {json.dumps(state, sort_keys=True)} -->"


class GitHub:
    """GitHub's REST API, with the token if there is one."""

    def __init__(self, token: str | None) -> None:
        """Remember the token."""
        self.token = token

    def call(self, method: str, path: str, data: dict[str, Any] | None = None) -> object:
        """Send one request; return the decoded JSON response."""
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        body = json.dumps(data).encode() if data is not None else None
        request = urllib.request.Request(API + path, data=body, headers=headers, method=method)  # noqa: S310 (fixed https URL)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310 (fixed https URL)
                return json.load(response)
        except (urllib.error.URLError, OSError, ValueError) as error:
            message = f"GitHub API {method} {path}: {error}"
            raise WatchError(message) from error

    def items(self, path: str) -> list[dict[str, Any]]:
        """Return a list response (one page)."""
        result = self.call("GET", path)
        if not isinstance(result, list):
            message = f"GitHub API {path}: expected a list"
            raise WatchError(message)
        return result

    def changed_files(self, base: str, head: str) -> list[dict[str, Any]]:
        """Return every file changed between two tags (the comparison is paged)."""
        files: list[dict[str, Any]] = []
        for page in range(1, MAX_PAGES + 1):
            result = self.call("GET", f"/repos/{UPSTREAM}/compare/{base}...{head}?per_page={PER_PAGE}&page={page}")
            batch = result.get("files", []) if isinstance(result, dict) else []
            files += batch
            if len(batch) < PER_PAGE:
                break
        return files


def run(command: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run a command from the checkout, capturing its output."""
    return subprocess.run(command, capture_output=True, text=True, check=False, cwd=ROOT, env=env)  # noqa: S603 (fixed commands)


def pinned_image() -> str:
    """Return the Kometa image pinned in compose.yaml."""
    env = {key: value for key, value in os.environ.items() if key != "KOMETA_IMAGE"}
    result = run(["bash", str(VALIDATE), "--print-image"], env)
    if result.returncode != 0:
        message = f"can't read Kometa's image from compose.yaml: {result.stderr.strip()}"
        raise WatchError(message)
    return result.stdout.strip()


def image_digest(name: str, tag: str) -> str:
    """Return the digest of name:tag in its registry (the multi-platform index, as Dependabot pins it)."""
    result = run(
        ["docker", "buildx", "imagetools", "inspect", f"{name}:{tag}", "--format", "{{json .Manifest.Digest}}"]
    )
    try:
        digest = json.loads(result.stdout) if result.returncode == 0 else None
    except ValueError:
        digest = None
    if not (isinstance(digest, str) and digest.startswith("sha256:")):
        message = f"can't resolve the digest of {name}:{tag}: {result.stderr.strip()}"
        raise WatchError(message)
    return digest


def validate(image: str) -> tuple[bool, str]:
    """Validate kometa/ against image and its release's schemas; return (passed, Kometa's report)."""
    env = {key: value for key, value in os.environ.items() if key != "KOMETA_SCHEMA_PATH"}
    env["KOMETA_IMAGE"] = image
    result = run(["bash", str(VALIDATE)], env)
    if result.returncode not in (0, VALIDATION_FAILED):
        message = f"kometa-validate.sh couldn't run: {result.stderr.strip() or result.stdout.strip()}"
        raise WatchError(message)
    lines = result.stdout.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("Kometa config (")), -1)
    return result.returncode == 0, "\n".join(lines[start + 1 :]).strip("\n")


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
            {"body": f"Back in step: compose.yaml pins {findings.latest}, the latest release, and kometa/ validates."},
        )
        github.call("PATCH", path, {"state": "closed", "state_reason": "completed"})
    return str(issue.get("html_url", ""))


def post(url: str, data: bytes, headers: dict[str, str]) -> None:
    """POST data to a notification endpoint."""
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")  # noqa: S310 (https checked by notify)
    with urllib.request.urlopen(request, timeout=TIMEOUT):  # noqa: S310 (https checked by notify)
        pass


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
    """Compare the pinned image with Kometa's latest release."""
    name, tag, _ = split_image(pinned)
    newer = releases_after(github.items(f"/repos/{UPSTREAM}/releases?per_page={PER_PAGE}"), tag)
    latest = newer[-1].tag if newer else tag
    digest = image_digest(name, latest)
    passed, report = validate(f"{name}:{latest}@{digest}")
    texts = [path.read_text(encoding="utf-8") for path in sorted((ROOT / "kometa").glob("*.yml"))]
    findings = Findings(pinned, latest, digest, newer, passed, report, note_excerpts(newer, words_in(texts)))
    if latest != tag:
        findings.patches = defaults_patches(github.changed_files(tag, latest), default_names(texts))
    return findings


def main(argv: list[str] | None = None) -> int:
    """Run the watch."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="print the action and the issue body; change nothing")
    parser.add_argument("--pinned", help="pretend this image is pinned (name:vX.Y.Z@sha256:...)")
    parser.add_argument("--existing-body", type=Path, help="with --dry-run: the open issue's body, instead of GitHub's")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY") or DEFAULT_REPO, help="OWNER/NAME")
    args = parser.parse_args(argv)
    github = GitHub(os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))
    try:
        findings = gather(github, args.pinned or pinned_image())
        if args.dry_run and args.existing_body:
            issue: dict[str, Any] | None = {"number": 0, "state": "open", "body": args.existing_body.read_text()}
        else:
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
        sent = notify(f"Kometa upstream: {findings.summary()} {url}", dict(os.environ))
        print(f"Alerts sent: {', '.join(sent) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
