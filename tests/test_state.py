"""Tests for state management — PRRecord and RepoState."""

from __future__ import annotations

from pr_review_bot.state import PRRecord, RepoState


class TestPRRecord:
    """Unit tests for PRRecord."""

    def test_to_dict_roundtrip(self):
        rec = PRRecord(
            number=42,
            title="Fix thing",
            author="dev",
            status="pending_review",
            queued_at="2026-04-29T00:00:00Z",
        )
        d = rec.to_dict()
        rec2 = PRRecord.from_dict(d)
        assert rec2.number == 42
        assert rec2.title == "Fix thing"
        assert rec2.status == "pending_review"

    def test_from_dict_defaults(self):
        rec = PRRecord.from_dict({"number": 1})
        assert rec.title == ""
        assert rec.status == "pending_review"
        assert rec.comment_id is None

    def test_status_transitions(self):
        rec = PRRecord(number=1, title="", author="", status="pending_review")
        assert rec.status == "pending_review"


class TestRepoState:
    """Unit tests for RepoState."""

    def test_mark_seen(self, tmp_path):
        state = RepoState(repo="Org/repo", state_file=tmp_path / "state.json")
        rec = state.mark_seen(1, "Fix bug", "dev1")
        assert rec.number == 1
        assert rec.status == "pending_review"
        assert 1 in state.prs

    def test_unseen_prs(self, tmp_path):
        state = RepoState(repo="Org/repo", state_file=tmp_path / "state.json")
        state.mark_seen(1, "PR 1", "dev1")
        state.mark_seen(3, "PR 3", "dev3")
        unseen = state.unseen_prs([1, 2, 3, 4])
        assert unseen == [2, 4]

    def test_mark_reviewed(self, tmp_path):
        state = RepoState(repo="Org/repo", state_file=tmp_path / "state.json")
        state.mark_seen(1, "Fix bug", "dev1")
        state.mark_reviewed(1, "lgtm")
        assert state.prs[1].status == "reviewed"
        assert state.prs[1].verdict == "lgtm"

    def test_mark_commented(self, tmp_path):
        state = RepoState(repo="Org/repo", state_file=tmp_path / "state.json")
        state.mark_seen(1, "Fix bug", "dev1")
        state.mark_commented(1, comment_id=12345)
        assert state.prs[1].status == "commented"
        assert state.prs[1].comment_id == 12345

    def test_mark_failed(self, tmp_path):
        state = RepoState(repo="Org/repo", state_file=tmp_path / "state.json")
        state.mark_seen(1, "Fix bug", "dev1")
        state.mark_failed(1, "network error")
        assert state.prs[1].status == "failed"
        assert state.prs[1].error == "network error"

    def test_pending_reviews(self, tmp_path):
        state = RepoState(repo="Org/repo", state_file=tmp_path / "state.json")
        state.mark_seen(1, "PR 1", "dev1")
        state.mark_seen(2, "PR 2", "dev2")
        state.mark_commented(2, comment_id=99)
        state.mark_seen(3, "PR 3", "dev3")
        state.mark_failed(3, "error")
        pending = state.pending_reviews()
        numbers = [r.number for r in pending]
        assert 1 in numbers  # pending_review
        assert 2 not in numbers  # already commented
        assert 3 in numbers  # failed = retry

    def test_save_and_load(self, tmp_path):
        state_file = tmp_path / "state.json"
        state = RepoState(repo="Org/repo", state_file=state_file)
        state.mark_seen(1, "Fix bug", "dev1")
        state.mark_reviewed(1, "needs_changes")
        state.save()

        loaded = RepoState.load("Org/repo", state_file)
        assert 1 in loaded.prs
        assert loaded.prs[1].status == "reviewed"
        assert loaded.prs[1].verdict == "needs_changes"

    def test_load_missing_file(self, tmp_path):
        state = RepoState.load("Org/repo", tmp_path / "nonexistent.json")
        assert len(state.prs) == 0
        assert state.repo == "Org/repo"

    def test_load_corrupt_file(self, tmp_path):
        state_file = tmp_path / "corrupt.json"
        state_file.write_text("not valid json{{{")
        state = RepoState.load("Org/repo", state_file)
        assert len(state.prs) == 0

    def test_state_persists_across_instances(self, tmp_path):
        state_file = tmp_path / "state.json"
        s1 = RepoState(repo="Org/repo", state_file=state_file)
        s1.mark_seen(10, "First PR", "dev")
        s1.save()

        s2 = RepoState.load("Org/repo", state_file)
        unseen = s2.unseen_prs([10, 20])
        assert unseen == [20]  # 10 already seen
