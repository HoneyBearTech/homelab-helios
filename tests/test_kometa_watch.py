import io
import json
import subprocess
import urllib.error
from typing import TYPE_CHECKING, Any, Self

import kometa_watch as kw
import pytest

if TYPE_CHECKING:
    from pathlib import Path

DIGEST = "sha256:" + "a" * 64
NEW_DIGEST = "sha256:" + "b" * 64
PINNED = f"kometateam/kometa:v2.5.0@{DIGEST}"


def release(tag: str, body: str = "", **extra: object) -> dict[str, Any]:
    return {"tag_name": tag, "html_url": f"https://example.com/{tag}", "body": body, **extra}


def findings(**changes: object) -> kw.Findings:
    values: dict[str, Any] = {
        "pinned": PINNED,
        "latest": "v2.5.2",
        "digest": NEW_DIGEST,
        "newer": [kw.Release("v2.5.1", "https://example.com/v2.5.1", ""), kw.Release("v2.5.2", "u", "")],
        "passed": True,
        "report": " Result: PASSED",
    }
    values.update(changes)
    return kw.Findings(**values)


# --- pure helpers -------------------------------------------------------------------------------------------------


def test_split_image() -> None:
    assert kw.split_image(PINNED) == ("kometateam/kometa", "v2.5.0", DIGEST)
    with pytest.raises(kw.WatchError):
        kw.split_image("kometateam/kometa:nightly")


def test_version() -> None:
    assert kw.version("v2.10.3") == (2, 10, 3)
    assert kw.version("nightly") is None


def test_releases_after_keeps_newer_published_versions_in_order() -> None:
    raw = [
        release("v2.5.2"),
        release("v2.6.0", prerelease=True),
        release("v2.5.3", draft=True),
        release("prerelease"),
        release("v2.5.0"),
        release("v2.5.1"),
    ]
    assert [r.tag for r in kw.releases_after(raw, "v2.5.0")] == ["v2.5.1", "v2.5.2"]
    assert [r.tag for r in kw.releases_after(raw, "nightly")] == ["v2.5.0", "v2.5.1", "v2.5.2"]


def test_words_and_default_names() -> None:
    texts = ["settings:\n  sync_mode: append\n  cache: true\ncollection_files:\n- default: imdb\n- default: basic\n"]
    assert kw.words_in(texts) == {"sync_mode", "collection_files", "basic", "imdb"}
    assert kw.default_names(texts) == {"imdb", "basic"}


def test_sanitize() -> None:
    assert kw.sanitize("a <!-- b --> c") == "a <!- - b - -> c"


def test_note_excerpts() -> None:
    body = "### Fixed\n\n- Fix the `sync_mode` of x\n- Deprecate the foo builder\n- Unrelated\nnot a bullet sync_mode\n"
    rel = kw.Release("v1.0.1", "u", body)
    assert kw.note_excerpts([rel, kw.Release("v1.0.2", "u", "- nothing here")], {"sync_mode"}) == [
        (rel, ["- Fix the `sync_mode` of x _(ours: sync_mode)_", "- Deprecate the foo builder"])
    ]
    assert kw.note_excerpts([rel], set()) == [(rel, ["- Deprecate the foo builder"])]


def test_defaults_patches() -> None:
    files = [
        {"filename": "defaults/overlays/resolution.yml", "patch": "@@ -1 +1 @@"},
        {"filename": "defaults/both/streaming.yml"},
        {"filename": "defaults/both/genre.yml", "patch": "x"},
        {"filename": "modules/resolution.yml", "patch": "x"},
        {"filename": "defaults/overlays/resolution.png"},
    ]
    assert kw.defaults_patches(files, {"resolution", "streaming"}) == [
        ("defaults/both/streaming.yml", "(no diff shown: too large; see the comparison link)"),
        ("defaults/overlays/resolution.yml", "@@ -1 +1 @@"),
    ]


def test_state_round_trip_and_bad_markers() -> None:
    state = {"latest": "v2.5.2", "digest": DIGEST}
    body = f'<!-- {kw.MARKER} {{"fake": 1}} -->\ntext\n{kw.state_comment(state)}'
    assert kw.parse_state(body) == state
    assert kw.parse_state(None) is None
    assert kw.parse_state(f"<!-- {kw.MARKER} {{not json}} -->") is None


def test_parse_state_rejects_a_non_object(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kw.json, "loads", lambda _: [1])
    assert kw.parse_state(f"<!-- {kw.MARKER} {{}} -->") is None


@pytest.mark.parametrize(
    ("in_step", "issue", "expected"),
    [
        (True, None, "nothing"),
        (True, {"state": "closed"}, "nothing"),
        (True, {"state": "open"}, "close"),
        (False, None, "create"),
        (False, {"state": "closed", "body": "x"}, "reopen"),
        (False, {"state": "open", "body": kw.state_comment({"a": "1"})}, "nothing"),
        (False, {"state": "open", "body": kw.state_comment({"a": "2"})}, "update"),
    ],
)
def test_decide(in_step: bool, issue: dict[str, Any] | None, expected: str) -> None:  # noqa: FBT001
    assert kw.decide(in_step=in_step, issue=issue, state={"a": "1"}) == expected


def test_findings_state_and_in_step() -> None:
    behind = findings()
    assert not behind.in_step
    assert behind.state()["pinned"] == "v2.5.0"
    assert "does NOT validate" in findings(passed=False).summary()
    current = findings(pinned=f"kometateam/kometa:v2.5.2@{NEW_DIGEST}", newer=[])
    assert current.in_step
    assert not findings(pinned=f"kometateam/kometa:v2.5.2@{NEW_DIGEST}", passed=False).in_step


def test_render_with_everything() -> None:
    rel = kw.Release("v2.5.1", "u", "")
    body = kw.render(findings(excerpts=[(rel, ["- a bullet"])], patches=[("defaults/x.yml", "+y" * 4000)]))
    assert "Newer releases: [v2.5.1]" in body
    assert "- a bullet" in body
    assert "... (cut; see the comparison)" in body
    assert body.endswith(kw.state_comment(findings(patches=[("defaults/x.yml", "+y" * 4000)]).state()))


def test_render_variants() -> None:
    same_tag = kw.render(findings(pinned=f"kometateam/kometa:v2.5.2@{DIGEST}", newer=[]))
    assert "now has another digest" in same_tag
    assert "No release-note bullet" in same_tag
    assert "None of the `defaults/` files" in same_tag
    nothing_new = kw.render(findings(pinned=f"kometateam/kometa:v2.5.2@{NEW_DIGEST}", newer=[], passed=False))
    assert "No newer release." in nothing_new
    assert ": failed" in nothing_new


def test_render_patches_stays_within_budget() -> None:
    many = findings(patches=[(f"defaults/{i}.yml", "+x" * 2000) for i in range(10)])
    text = kw.render_patches(many, budget=9000)
    assert text.count("<details>") == 2  # each diff is ~4 KB; the third would pass the budget
    assert "... and more" in text


# --- GitHub ---------------------------------------------------------------------------------------------------------


class FakeResponse(io.BytesIO):
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def test_github_call_sends_the_token(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Any] = []

    def urlopen(request: urllib.request.Request, timeout: int) -> FakeResponse:
        seen.append((request, timeout))
        return FakeResponse(b'{"ok": true}')

    monkeypatch.setattr(kw.urllib.request, "urlopen", urlopen)
    assert kw.GitHub("t0k").call("POST", "/x", {"a": 1}) == {"ok": True}
    request = seen[0][0]
    assert request.get_header("Authorization") == "Bearer t0k"
    assert request.data == b'{"a": 1}'
    assert kw.GitHub(None).call("GET", "/x") == {"ok": True}
    assert seen[1][0].get_header("Authorization") is None


def test_github_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_: object, **__: object) -> None:
        reason = "down"
        raise urllib.error.URLError(reason)

    monkeypatch.setattr(kw.urllib.request, "urlopen", fail)
    with pytest.raises(kw.WatchError, match="down"):
        kw.GitHub(None).call("GET", "/x")
    monkeypatch.setattr(kw.GitHub, "call", lambda *_: {"not": "a list"})
    with pytest.raises(kw.WatchError, match="expected a list"):
        kw.GitHub(None).items("/x")


def test_changed_files_follows_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = [{"files": [{"filename": str(i)} for i in range(kw.PER_PAGE)]}, {"files": [{"filename": "last"}]}]
    monkeypatch.setattr(kw.GitHub, "call", lambda *_: pages.pop(0))
    assert len(kw.GitHub(None).changed_files("v1.0.0", "v1.0.1")) == kw.PER_PAGE + 1
    monkeypatch.setattr(kw.GitHub, "call", lambda *_: [])
    assert kw.GitHub(None).changed_files("v1.0.0", "v1.0.1") == []


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
    return {"number": number, "state": state, "title": kw.TITLE, "body": kw.state_comment({}), **extra}


def test_find_issue() -> None:
    assert kw.find_issue(FakeGitHub({"/repos/o/r/issues": []}), "o/r") is None
    issues = [
        issue(3, "closed"),
        issue(9, "closed"),
        issue(5, "open", pull_request={}),
        issue(6, "open", title="Other"),
        issue(7, "open", body="no marker"),
    ]
    assert kw.find_issue(FakeGitHub({"/repos/o/r/issues": issues}), "o/r")["number"] == 9
    assert kw.find_issue(FakeGitHub({"/repos/o/r/issues": [*issues, issue(4, "open")]}), "o/r")["number"] == 4


def test_apply_each_action() -> None:
    github = FakeGitHub({"/repos/o/r/issues": {"html_url": "https://example.com/1"}})
    assert kw.apply(github, "o/r", "create", None, findings()) == "https://example.com/1"
    assert github.calls[0][2]["title"] == kw.TITLE
    assert kw.apply(FakeGitHub({"/repos/o/r/issues": []}), "o/r", "create", None, findings()) == ""
    assert kw.apply(FakeGitHub(), "o/r", "nothing", None, findings()) == ""

    existing = issue(1, "open", html_url="https://example.com/1")
    for action, first_call in [("update", "PATCH"), ("reopen", "PATCH"), ("close", "POST"), ("nothing", None)]:
        github = FakeGitHub()
        assert kw.apply(github, "o/r", action, existing, findings()) == "https://example.com/1"
        assert (github.calls[0][0] if github.calls else None) == first_call
    github = FakeGitHub()
    kw.apply(github, "o/r", "reopen", existing, findings())
    assert github.calls[1][2]["body"].startswith("Reopened: ")


# --- commands -------------------------------------------------------------------------------------------------------


def completed(code: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], code, stdout, stderr)


def test_run_runs_from_the_checkout() -> None:
    assert kw.run(["python3", "-c", "import os; print(os.getcwd())"]).stdout.strip() == str(kw.ROOT)


def test_pinned_image(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KOMETA_IMAGE", "elsewhere")
    seen: list[dict[str, str]] = []

    def run(_: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        seen.append(env)
        return completed(0, PINNED + "\n")

    monkeypatch.setattr(kw, "run", run)
    assert kw.pinned_image() == PINNED
    assert "KOMETA_IMAGE" not in seen[0]
    monkeypatch.setattr(kw, "run", lambda *_: completed(2, stderr="no compose"))
    with pytest.raises(kw.WatchError, match="no compose"):
        kw.pinned_image()


@pytest.mark.parametrize(
    ("result", "ok"),
    [
        (completed(0, json.dumps(DIGEST)), True),
        (completed(0, "not json"), False),
        (completed(0, '"latest"'), False),
        (completed(1, "", "unauthorized"), False),
    ],
)
def test_image_digest(monkeypatch: pytest.MonkeyPatch, result: subprocess.CompletedProcess[str], ok: bool) -> None:  # noqa: FBT001
    monkeypatch.setattr(kw, "run", lambda *_: result)
    if ok:
        assert kw.image_digest("kometateam/kometa", "v2.5.2") == DIGEST
    else:
        with pytest.raises(kw.WatchError):
            kw.image_digest("kometateam/kometa", "v2.5.2")


def test_validate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KOMETA_SCHEMA_PATH", "/old")
    output = "Fetching\nValidating\nKometa config (kometa, img): passed\n Result: PASSED\n"
    seen: list[dict[str, str]] = []

    def run(_: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        seen.append(env)
        return completed(0, output)

    monkeypatch.setattr(kw, "run", run)
    assert kw.validate("img") == (True, " Result: PASSED")
    assert seen[0]["KOMETA_IMAGE"] == "img"
    assert "KOMETA_SCHEMA_PATH" not in seen[0]
    monkeypatch.setattr(kw, "run", lambda *_: completed(1, output))
    assert kw.validate("img")[0] is False
    monkeypatch.setattr(kw, "run", lambda *_: completed(2, "", "No Kometa JSON schemas"))
    with pytest.raises(kw.WatchError, match="schemas"):
        kw.validate("img")


# --- alerts -----------------------------------------------------------------------------------------------------------


def test_post(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Any] = []
    monkeypatch.setattr(kw.urllib.request, "urlopen", lambda request, **_: seen.append(request) or FakeResponse())
    kw.post("https://ntfy.example.com/x", b"hi", {"Title": "t"})
    assert seen[0].data == b"hi"


def test_notify(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    sent: list[str] = []
    monkeypatch.setattr(kw, "post", lambda url, *_: sent.append(url))
    assert kw.notify("hi", {}) == []
    env = {"NTFY_URL": "https://ntfy.example.com/x", "DISCORD_WEBHOOK": "https://discord.example.com/y"}
    assert kw.notify("hi", env) == ["ntfy", "discord"]
    assert kw.notify("hi", {"NTFY_URL": "http://ntfy.example.com/x"}) == []
    assert "not an https URL" in capsys.readouterr().out

    def fail(*_: object) -> None:
        reason = "refused"
        raise urllib.error.URLError(reason)

    monkeypatch.setattr(kw, "post", fail)
    assert kw.notify("hi", env) == []
    assert "the alert failed" in capsys.readouterr().out


# --- the whole run ----------------------------------------------------------------------------------------------------


@pytest.fixture
def upstream(monkeypatch: pytest.MonkeyPatch) -> FakeGitHub:
    github = FakeGitHub(
        {
            f"/repos/{kw.UPSTREAM}/releases": [release("v2.5.1", "- Fix sync_mode"), release("v2.5.0")],
            f"/repos/{kw.UPSTREAM}/compare/": {"files": [{"filename": "defaults/chart/imdb.yml", "patch": "+x"}]},
            "/repos/o/r/issues": [],
        }
    )
    monkeypatch.setattr(kw, "GitHub", lambda _: github)
    monkeypatch.setattr(kw, "pinned_image", lambda: PINNED)
    monkeypatch.setattr(kw, "image_digest", lambda *_: NEW_DIGEST)
    monkeypatch.setattr(kw, "validate", lambda _: (True, " Result: PASSED"))
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.delenv("NTFY_URL", raising=False)
    monkeypatch.delenv("DISCORD_WEBHOOK", raising=False)
    return github


def test_gather(upstream: FakeGitHub) -> None:
    found = kw.gather(upstream, PINNED)
    assert found.latest == "v2.5.1"
    assert found.patches == [("defaults/chart/imdb.yml", "+x")]
    assert found.excerpts
    current = kw.gather(upstream, f"kometateam/kometa:v2.5.1@{NEW_DIGEST}")
    assert current.in_step
    assert current.patches == []


def test_main_creates_the_issue_and_alerts(
    upstream: FakeGitHub, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    alerts: list[str] = []
    monkeypatch.setattr(kw, "notify", lambda text, _: alerts.append(text) or ["ntfy"])
    assert kw.main([]) == 0
    assert ("POST", "/repos/o/r/issues", upstream.calls[-1][2]) in upstream.calls
    assert alerts
    assert "Alerts sent: ntfy" in capsys.readouterr().out


def test_main_in_step_does_nothing(upstream: FakeGitHub, capsys: pytest.CaptureFixture[str]) -> None:
    assert kw.main(["--pinned", f"kometateam/kometa:v2.5.1@{NEW_DIGEST}"]) == 0
    assert "nothing: no issue" in capsys.readouterr().out
    assert all(method == "GET" for method, _, _ in upstream.calls)


def test_main_dry_run(upstream: FakeGitHub, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert kw.main(["--dry-run"]) == 0
    first = capsys.readouterr().out
    assert first.startswith("Action: create")
    body = tmp_path / "body.md"
    body.write_text(first.split("\n", 2)[2])
    assert kw.main(["--dry-run", "--existing-body", str(body)]) == 0
    assert capsys.readouterr().out.startswith("Action: nothing")
    assert all(method == "GET" for method, _, _ in upstream.calls)


def test_main_reports_what_it_couldnt_check(
    upstream: FakeGitHub, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert upstream

    def broken() -> str:
        message = "no compose"
        raise kw.WatchError(message)

    monkeypatch.setattr(kw, "pinned_image", broken)
    assert kw.main([]) == 1
    assert "::error::no compose" in capsys.readouterr().out
