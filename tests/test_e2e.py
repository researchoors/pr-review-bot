"""End-to-end tests for complete PR detection → review → comment flows.

These tests simulate the full lifecycle:
  1. New PRs appear in a repo
  2. Poller detects them
  3. Review analysis is performed (simulated)
  4. Comment is posted
  5. Assurance check confirms comment exists

Run with: pytest -m e2e
Skip with: pytest -m "not e2e"
"""

from __future__ import annotations

import pytest

from pr_review_bot.github_client import PRInfo
from pr_review_bot.poller import poll_repo
from pr_review_bot.poster import ensure_all_commented, post_pending_comments
from pr_review_bot.state import RepoState


@pytest.fixture
def e2e_env(sample_repo_config, mock_github_client):
    """Full E2E environment with mock GitHub client and state."""
    return {
        "config": sample_repo_config,
        "client": mock_github_client,
    }


class TestE2EFlow:
    """E2E: PR detection → ingestion → review → comment."""

    @pytest.mark.e2e
    def test_full_flow_single_pr(self, e2e_env):
        """A new PR appears, gets detected, reviewed, and commented."""
        config = e2e_env["config"]
        client = e2e_env["client"]

        # Step 1: PR appears in the repo
        pr = PRInfo(
            number=42, title="Fix auth bypass", author="security-dev",
            branch="fix/auth-bypass", url="https://github.com/TestOrg/test-repo/pull/42",
            created_at="2026-04-29T00:00:00Z", updated_at="2026-04-29T00:00:00Z",
            head_sha="deadbeef", state="open",
        )
        client.list_open_prs.return_value = [pr]

        # Step 2: Poller detects the new PR
        new_prs = poll_repo(client, config)
        assert len(new_prs) == 1
        assert new_prs[0]["number"] == 42
        assert new_prs[0]["status"] == "pending_review"

        # Step 3: Simulate review analysis producing a review body
        review_body = (
            "## Hermes Agent Review\n\n"
            "**Verdict: Needs changes**\n\n"
            "🔴 Critical: Auth bypass in login path"
        )
        reviews = {42: review_body}

        # Step 4: Post the comment
        client.has_bot_comment.return_value = False
        client.post_comment.return_value = 55555
        results = post_pending_comments(client, config, reviews=reviews)

        assert len(results) == 1
        assert results[0]["status"] == "commented"
        assert results[0]["comment_id"] == 55555

        # Verify post_comment was called with the review body
        call_args = client.post_comment.call_args
        assert call_args[0][0] == "TestOrg/test-repo"
        assert call_args[0][1] == 42
        assert "Auth bypass" in call_args[0][2]

        # Step 5: Assurance check
        client.get_comments.return_value = [{"id": 55555}]
        unconfirmed = ensure_all_commented(client, config)
        assert len(unconfirmed) == 0

    @pytest.mark.e2e
    def test_full_flow_multiple_prs(self, e2e_env):
        """Multiple new PRs appear simultaneously."""
        config = e2e_env["config"]
        client = e2e_env["client"]

        prs = [
            PRInfo(number=i, title=f"PR #{i}", author=f"dev{i}",
                   branch=f"branch-{i}", url=f"http://example.com/{i}",
                   created_at="", updated_at="", head_sha=f"sha{i}", state="open")
            for i in range(1, 6)
        ]
        client.list_open_prs.return_value = prs

        # Poll
        new_prs = poll_repo(client, config)
        assert len(new_prs) == 5

        # Post comments for all
        client.has_bot_comment.return_value = False
        client.post_comment.return_value = 10001
        reviews = {i: f"Review for PR #{i}" for i in range(1, 6)}
        results = post_pending_comments(client, config, reviews=reviews)
        assert len(results) == 5
        assert all(r["status"] == "commented" for r in results)

    @pytest.mark.e2e
    def test_flow_with_transient_failure_then_retry(self, e2e_env):
        """Comment post fails first time, succeeds on retry."""
        config = e2e_env["config"]
        client = e2e_env["client"]

        pr = PRInfo(
            number=7, title="Feature X", author="dev",
            branch="feat/x", url="http://example.com/7",
            created_at="", updated_at="", head_sha="sha7", state="open",
        )
        client.list_open_prs.return_value = [pr]
        poll_repo(client, config)

        reviews = {7: "LGTM"}

        # First attempt fails
        client.has_bot_comment.return_value = False
        client.post_comment.return_value = None
        results1 = post_pending_comments(client, config, reviews=reviews)
        assert results1[0]["status"] == "failed"

        # Retry succeeds
        client.post_comment.return_value = 22222
        results2 = post_pending_comments(client, config, reviews=reviews)
        assert results2[0]["status"] == "commented"
        assert results2[0]["comment_id"] == 22222

    @pytest.mark.e2e
    def test_flow_duplicate_comment_prevention(self, e2e_env):
        """Bot doesn't double-comment if it already has a comment on the PR."""
        config = e2e_env["config"]
        client = e2e_env["client"]

        pr = PRInfo(
            number=8, title="Feature Y", author="dev",
            branch="feat/y", url="http://example.com/8",
            created_at="", updated_at="", head_sha="sha8", state="open",
        )
        client.list_open_prs.return_value = [pr]
        poll_repo(client, config)

        # First comment succeeds
        client.has_bot_comment.return_value = False
        client.post_comment.return_value = 33333
        results1 = post_pending_comments(client, config, reviews={8: "Review 1"})
        assert results1[0]["status"] == "commented"

        # Second call: PR already marked "commented" so it won't appear in pending_reviews.
        # This is the intended behavior — once commented, it's done.
        # To test the API-level dedup, reset state to "pending_review" (simulating a
        # scenario where state was lost but the comment still exists on GitHub)
        state = RepoState.load(config.owner_repo, config.state_file)
        state.prs[8].status = "pending_review"
        state.save()

        client.has_bot_comment.return_value = True  # GitHub says we already commented
        results2 = post_pending_comments(client, config, reviews={8: "Review 2"})
        assert results2[0]["status"] == "already_commented"
        # post_comment should NOT have been called again
        assert client.post_comment.call_count == 1

    @pytest.mark.e2e
    def test_flow_new_prs_amidst_existing(self, e2e_env):
        """New PRs are detected even when many existing PRs are already tracked."""
        config = e2e_env["config"]
        client = e2e_env["client"]

        # Initial: 10 PRs
        old_prs = [
            PRInfo(number=i, title=f"PR #{i}", author="dev",
                   branch=f"b{i}", url=f"http://example.com/{i}",
                   created_at="", updated_at="", head_sha=f"sha{i}", state="open")
            for i in range(1, 11)
        ]
        client.list_open_prs.return_value = old_prs
        new = poll_repo(client, config)
        assert len(new) == 10

        # Mark all as commented
        state = RepoState.load(config.owner_repo, config.state_file)
        for pr_num in state.prs:
            state.mark_commented(pr_num, comment_id=pr_num * 100)
        state.save()

        # New PR appears: #15
        updated_prs = old_prs + [
            PRInfo(number=15, title="New hot PR", author="newdev",
                   branch="hot", url="http://example.com/15",
                   created_at="", updated_at="", head_sha="sha15", state="open"),
        ]
        client.list_open_prs.return_value = updated_prs
        new = poll_repo(client, config)
        assert len(new) == 1
        assert new[0]["number"] == 15

    @pytest.mark.e2e
    def test_flow_assurance_detects_deleted_comment(self, e2e_env):
        """Assurance check catches a comment that was deleted after posting."""
        config = e2e_env["config"]
        client = e2e_env["client"]

        pr = PRInfo(
            number=99, title="PR 99", author="dev",
            branch="b99", url="http://example.com/99",
            created_at="", updated_at="", head_sha="sha99", state="open",
        )
        client.list_open_prs.return_value = [pr]
        poll_repo(client, config)

        # Comment was posted
        client.has_bot_comment.return_value = False
        client.post_comment.return_value = 44444
        post_pending_comments(client, config, reviews={99: "Review"})

        # But now the comment was deleted (or the API is returning different data)
        client.get_comments.return_value = []  # Comment gone
        unconfirmed = ensure_all_commented(client, config)
        assert len(unconfirmed) == 1
        assert unconfirmed[0]["status"] == "comment_missing"
