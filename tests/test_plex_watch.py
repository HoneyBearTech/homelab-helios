import urllib.error
from typing import TYPE_CHECKING, Any

import kometa_watch as kw
import plex_watch as pw
import pytest

if TYPE_CHECKING:
    from pathlib import Path

DIGEST = "sha256:" + "a" * 64
NEW_DIGEST = "sha256:" + "b" * 64
OLD = "1.43.3.10896-cb3ebc72d-ls323"
REBUILD = "1.43.3.10896-cb3ebc72d-ls324"
NEW = "1.43.4.10903-e5521bd8c-ls325"
PINNED = f"{pw.IMAGE}:{OLD}@{DIGEST}"


def release(tag: str, **extra: object) -> dict[str, Any]:
    return {
        "tag_name": tag,
        "html_url": f"https://example.com/{tag}",
        "published_at": "2026-10-05T18:29:55Z",
        **extra,
    }


def build(tag: str) -> pw.Build:
    return pw.Build(tag, f"https://example.com/{tag}", "2026-10-05")


def findings(**changes: object) -> pw.Findings:
    values: dict[str, Any] = {
        "pinned": PINNED,
        "latest": NEW,
        "digest": NEW_DIGEST,
        "newer": [build(REBUILD), build(NEW)],
    }
    values.update(changes)
    return pw.Findings(**values)


class FakeGitHub(kw.GitHub):
    def __init__(self, responses: dict[str, object] | None = None) -> None:
        super().__init__(None)
        self.responses = responses or {}
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def call(self, method: str, path: str, data: dict[str, Any] | None = None) -> object:
        self.calls.append((method, path, data))
        for prefix, response in self.responses.items():
            if path.startswith(prefix):
                return response
        return {}


def issue(number: int, state: str, **extra: object) -> dict[str, Any]:
    return {"number": number, "state": state, "title": pw.TITLE, "body": pw.state_comment({}), **extra}


# --- pure helpers -------------------------------------------------------------------------------------------------


def test_split_image_and_sort_key() -> None:
    assert pw.split_image(PINNED) == (pw.IMAGE, OLD, DIGEST)
    with pytest.raises(kw.WatchError):
        pw.split_image(f"{pw.IMAGE}:version-1.43.4.10903-e5521bd8c@{DIGEST}")
    with pytest.raises(kw.WatchError):
        pw.split_image(f"{pw.IMAGE}:{OLD}")
    assert pw.sort_key(NEW) == (1, 43, 4, 10903, 325)
    assert pw.sort_key("latest") is None
    assert build(NEW).plex_version == "1.43.4.10903-e5521bd8c"


def test_builds_after_keeps_newer_published_builds_in_order() -> None:
    raw = [
        release(NEW),
        release("1.43.5.11000-abcdef123-ls326", prerelease=True),
        release("1.43.5.11000-abcdef123-ls327", draft=True),
        release(REBUILD),
        release(OLD),
        release("1.43.2.10000-0123456789-ls300"),
        release("not-a-build"),
    ]
    assert [b.tag for b in pw.builds_after(raw, OLD)] == [REBUILD, NEW]
    assert pw.builds_after(raw, OLD)[0].published == "2026-10-05"
    # A pin the watch can't read: every published build counts as newer.
    assert len(pw.builds_after(raw, "latest")) == 4


def test_pinned_image(tmp_path: Path) -> None:
    compose = tmp_path / "compose.yaml"
    compose.write_text(f"services:\n  plex:\n    image: {PINNED}\n  other:\n    image: x/y:1@{DIGEST}\n")
    assert pw.pinned_image(compose) == PINNED
    compose.write_text("services: {}\n")
    with pytest.raises(kw.WatchError, match="found 0"):
        pw.pinned_image(compose)


def test_pinned_image_reads_the_repository_compose_file() -> None:
    assert pw.split_image(pw.pinned_image())[0] == pw.IMAGE


def test_state_round_trip_and_bad_markers() -> None:
    state = findings().state()
    assert pw.parse_state("text\n" + pw.state_comment(state)) == state
    assert pw.parse_state(None) is None
    assert pw.parse_state(f"<!-- {pw.MARKER} {{not json}} -->") is None


def test_parse_state_rejects_a_non_object(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pw.json, "loads", lambda _: ["a list"])
    assert pw.parse_state(pw.state_comment({})) is None


@pytest.mark.parametrize(
    ("in_step", "issue", "expected"),
    [
        (True, None, "nothing"),
        (True, {"state": "closed"}, "nothing"),
        (True, {"state": "open"}, "close"),
        (False, None, "create"),
        (False, {"state": "closed"}, "reopen"),
        (False, {"state": "open", "body": pw.state_comment({"a": "b"})}, "nothing"),
        (False, {"state": "open", "body": ""}, "update"),
    ],
)
def test_decide(in_step: bool, issue: dict[str, Any] | None, expected: str) -> None:  # noqa: FBT001
    assert pw.decide(in_step=in_step, issue=issue, state={"a": "b"}) == expected


def test_findings_in_step_and_summary() -> None:
    assert not findings().in_step
    assert "a new Plex version" in findings().summary()
    assert "a rebuild" in findings(latest=REBUILD, newer=[build(REBUILD)]).summary()
    same = findings(latest=OLD, digest=NEW_DIGEST, newer=[])
    assert "a new digest for the pinned build" in same.summary()
    current = findings(latest=OLD, digest=DIGEST, newer=[])
    assert current.in_step
    assert current.summary() == f"compose.yaml pins {OLD}, the newest Plex image."
    assert findings().state() == {"pinned": OLD, "latest": NEW, "digest": NEW_DIGEST}


def test_render_variants() -> None:
    body = pw.render(findings())
    assert f"[{NEW}](https://example.com/{NEW})" in body
    assert f"`image: {pw.IMAGE}:{NEW}@{NEW_DIGEST}`" in body
    assert pw.parse_state(body) == findings().state()
    assert "another digest" in pw.render(findings(latest=OLD, newer=[]))
    assert "the pin is the newest one" in pw.render(findings(latest=OLD, digest=DIGEST, newer=[]))


# --- GitHub ---------------------------------------------------------------------------------------------------------


def test_find_issue() -> None:
    assert pw.find_issue(FakeGitHub({"/repos/o/r/issues": []}), "o/r") is None
    issues = [
        issue(3, "closed"),
        issue(9, "closed"),
        issue(5, "open", pull_request={}),
        issue(6, "open", title="Kometa upstream changes"),
        issue(7, "open", body="no marker"),
    ]
    assert pw.find_issue(FakeGitHub({"/repos/o/r/issues": issues}), "o/r")["number"] == 9
    assert pw.find_issue(FakeGitHub({"/repos/o/r/issues": [*issues, issue(4, "open")]}), "o/r")["number"] == 4


def test_apply_each_action() -> None:
    github = FakeGitHub({"/repos/o/r/issues": {"html_url": "https://example.com/1"}})
    assert pw.apply(github, "o/r", "create", None, findings()) == "https://example.com/1"
    assert github.calls[0][2]["title"] == pw.TITLE
    assert pw.apply(FakeGitHub({"/repos/o/r/issues": []}), "o/r", "create", None, findings()) == ""
    assert pw.apply(FakeGitHub(), "o/r", "nothing", None, findings()) == ""

    existing = issue(1, "open", html_url="https://example.com/1")
    for action, first_call in [("update", "PATCH"), ("reopen", "PATCH"), ("close", "POST"), ("nothing", None)]:
        github = FakeGitHub()
        assert pw.apply(github, "o/r", action, existing, findings()) == "https://example.com/1"
        assert (github.calls[0][0] if github.calls else None) == first_call
    github = FakeGitHub()
    pw.apply(github, "o/r", "reopen", existing, findings())
    assert github.calls[1][2]["body"].startswith("Reopened: ")


def test_notify(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    sent: list[tuple[str, dict[str, str]]] = []

    def fake_post(url: str, _data: bytes, headers: dict[str, str]) -> None:
        if "fail" in url:
            reason = "down"
            raise urllib.error.URLError(reason)
        sent.append((url, headers))

    monkeypatch.setattr(pw, "post", fake_post)
    assert pw.notify("x", {}) == []
    assert pw.notify("x", {"NTFY_URL": "https://ntfy.example/t", "DISCORD_WEBHOOK": "https://d.example/w"}) == [
        "ntfy",
        "discord",
    ]
    assert sent[0][1]["Title"] == pw.TITLE
    assert pw.notify("x", {"NTFY_URL": "http://plain", "DISCORD_WEBHOOK": "https://fail.example"}) == []
    out = capsys.readouterr().out
    assert "not an https URL" in out
    assert "the alert failed" in out


# --- the run --------------------------------------------------------------------------------------------------------


@pytest.fixture
def upstream(monkeypatch: pytest.MonkeyPatch) -> FakeGitHub:
    github = FakeGitHub(
        {
            f"/repos/{pw.UPSTREAM}/releases": [release(NEW), release(REBUILD), release(OLD)],
            "/repos/o/r/issues": [],
        }
    )
    monkeypatch.setattr(pw, "GitHub", lambda _token: github)
    monkeypatch.setattr(pw, "image_digest", lambda _name, _tag: NEW_DIGEST)
    monkeypatch.setattr(pw, "post", lambda *_: None)
    return github


def test_gather(upstream: FakeGitHub) -> None:
    found = pw.gather(upstream, PINNED)
    assert (found.latest, found.digest, [b.tag for b in found.newer]) == (NEW, NEW_DIGEST, [REBUILD, NEW])
    current = pw.gather(FakeGitHub({f"/repos/{pw.UPSTREAM}/releases": [release(OLD)]}), PINNED)
    assert (current.latest, current.newer) == (OLD, [])


def test_main_creates_the_issue_and_alerts(
    upstream: FakeGitHub, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NTFY_URL", "https://ntfy.example/t")
    monkeypatch.delenv("DISCORD_WEBHOOK", raising=False)
    upstream.responses["/repos/o/r/issues"] = []
    assert pw.main(["--repo", "o/r", "--pinned", PINNED]) == 0
    assert any(method == "POST" and path == "/repos/o/r/issues" for method, path, _ in upstream.calls)
    out = capsys.readouterr().out
    assert "create:" in out
    assert "Alerts sent: ntfy" in out


@pytest.mark.usefixtures("upstream")
def test_main_in_step_does_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    assert pw.main(["--repo", "o/r", "--pinned", f"{pw.IMAGE}:{NEW}@{NEW_DIGEST}"]) == 0
    assert capsys.readouterr().out.startswith("nothing: no issue")


def test_main_dry_run(upstream: FakeGitHub, capsys: pytest.CaptureFixture[str]) -> None:
    assert pw.main(["--dry-run", "--repo", "o/r", "--pinned", PINNED]) == 0
    assert all(method == "GET" for method, _, _ in upstream.calls)
    assert capsys.readouterr().out.startswith("Action: create")


@pytest.mark.usefixtures("upstream")
def test_main_reports_what_it_couldnt_check(capsys: pytest.CaptureFixture[str]) -> None:
    assert pw.main(["--repo", "o/r", "--pinned", "bad"]) == 1
    assert "::error::" in capsys.readouterr().out
