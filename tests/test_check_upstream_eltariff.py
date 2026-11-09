"""Tests for the upstream release monitor."""

import io
import json
import tarfile

import pytest

from scripts import check_upstream_eltariff as monitor


def _archive(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name, content in files.items():
            member = tarfile.TarInfo(f"release/specification/{name}")
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    return output.getvalue()


def test_fingerprints_ignore_formatting_and_key_order() -> None:
    first = monitor.fingerprint_archive(_archive({"schema.json": b'{"b": 2, "a": 1}'}))
    second = monitor.fingerprint_archive(_archive({"schema.json": b'{ "a": 1,"b":2 }'}))
    assert first == second


def test_added_removed_and_referenced_schemas_are_reported() -> None:
    before = monitor.fingerprint_archive(
        _archive({"gridtariffapi.json": b"{}", "price.schema.json": b'{"v":1}', "old.json": b"[]"})
    )
    after = monitor.fingerprint_archive(
        _archive({"gridtariffapi.json": b"{}", "price.schema.json": b'{"v":2}', "new.json": b"[]"})
    )
    assert monitor.changes(before, after) == [
        ("Added", "new.json"),
        ("Removed", "old.json"),
        ("Changed", "price.schema.json"),
    ]


@pytest.mark.parametrize("files", [{}, {"schema.json": b"invalid json"}])
def test_invalid_release_is_not_treated_as_synchronized(files: dict[str, bytes]) -> None:
    with pytest.raises(ValueError):
        monitor.fingerprint_archive(_archive(files))


def test_archive_rejects_duplicate_members() -> None:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for _ in range(2):
            member = tarfile.TarInfo("release/specification/a.json")
            member.size = 2
            archive.addfile(member, io.BytesIO(b"{}"))
    with pytest.raises(ValueError, match="Invalid specification"):
        monitor.fingerprint_archive(output.getvalue())


@pytest.mark.parametrize("existing", [False, True])
def test_report_creates_or_updates_one_marked_issue(monkeypatch, existing: bool) -> None:
    calls = []

    def fake_gh(*args):
        calls.append(args)
        if len(calls) == 1:
            issues = [{"number": 42, "body": monitor.MARKER}] if existing else []
            return json.dumps([[], issues]).encode()
        return b'{"html_url":"https://github.com/example/repo/issues/42"}'

    monkeypatch.setattr(monitor, "gh", fake_gh)
    result = monitor.report_issue("example/repo", {"tag_name": "v0.5.0"}, "body")
    assert result.endswith("/42")
    assert calls[0][-2:] == ("--paginate", "--slurp")
    endpoint = "repos/example/repo/issues/42" if existing else "repos/example/repo/issues"
    assert calls[1][0] == endpoint
    assert ("PATCH" if existing else "POST") in calls[1]


def test_duplicate_issues_fail_without_writing(monkeypatch) -> None:
    issues = [[{"number": 1, "body": monitor.MARKER}, {"number": 2, "body": monitor.MARKER}]]
    calls = []

    def fake_gh(*args):
        calls.append(args)
        return json.dumps(issues).encode()

    monkeypatch.setattr(monitor, "gh", fake_gh)
    with pytest.raises(ValueError, match="More than one"):
        monitor.report_issue("example/repo", {"tag_name": "v1"}, "body")
    assert len(calls) == 1


def test_issue_body_links_releases_and_describes_manual_review() -> None:
    body = monitor.issue_body(
        {"release": "v0.4.0"},
        {
            "tag_name": "v0.5.0",
            "html_url": "https://github.com/RI-SE/Eltariff-API/releases/tag/v0.5.0",
            "published_at": "2026-10-22T00:00:00Z",
        },
        [("Changed", "price.schema.json")],
    )
    assert "compare/v0.4.0...v0.5.0" in body
    assert "price.schema.json" in body
    assert "--write-baseline" in body
    assert monitor.MARKER in body


def test_unchanged_specification_does_not_create_issue(monkeypatch, tmp_path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"release": "v1", "files": {"a.json": "123"}}))
    monkeypatch.setattr(monitor, "BASELINE", baseline)
    monkeypatch.setattr(monitor, "latest_release", lambda: ({"tag_name": "v2"}, {"a.json": "123"}))
    monkeypatch.setattr(monitor.sys, "argv", ["check_upstream_eltariff.py"])

    def unexpected_report(*args):
        raise AssertionError("Should not create an issue for an unchanged specification")

    monkeypatch.setattr(monitor, "report_issue", unexpected_report)
    monitor.main()
