"""Tests for the comment poster module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from pr_review_bot.github_client import PRInfo
from pr_review_bot.poller import poll_repo
from pr_review_bot.poster import ensure_all_commented, post_pending_comments


class TestPostPendingComments:
    """Tests for post_pending_comments()."""

    def test_posts_comment_for_pending_review(self, sample_repo_config, sample_prs, mock_github_client):
        # Set up: poll to get PRs into state
        mock_github_client.list_open_prs.return_value = sample_prs
        poll_repo(mock_github_client, sample_repo_config)

        # Now post comments
        mock_github_client.has_bot_comment.return_value = False
        mock_github_client.post_comment.return_value = 99999

        reviews = {1: "LGTM", 2: "Needs work", 3: "Minor suggestions"}
        results = post_pending_comments(
            mock_github_client, sample_repo_config,
            bot_login="hankbobtheresearchoor",
            reviews=reviews,
        )

        assert len(results) == 3
        assert all(r["status"] == "commented" for r in results)
        mock_github_client.post_comment.assert_called()

    def test_skips_already_commented_prs(self, sample_repo_config, sample_prs, mock_github_client):
        # Poll to get PRs into state
        mock_github_client.list_open_prs.return_value = sample_prs
        poll_repo(mock_github_client, sample_repo_config)

        # Bot already commented on PR #1
        def has_comment(repo, pr_num, login):
            return pr_num == 1
        mock_github_client.has_bot_comment.side_effect = has_comment
        mock_github_client.post_comment.return_value = 88888

        reviews = {1: "LGTM", 2: "Needs work"}
        results = post_pending_comments(
            mock_github_client, sample_repo_config,
            bot_login="hankbobtheresearchoor",
            reviews=reviews,
        )

        statuses = {r["number"]: r["status"] for r in results}
        assert statuses[1] == "already_commented"
        assert statuses[2] == "commented"

    def test_handles_post_failure(self, sample_repo_config, sample_prs, mock_github_client):
        # Poll to get PRs into state
        mock_github_client.list_open_prs.return_value = [sample_prs[0]]
        poll_repo(mock_github_client, sample_repo_config)

        mock_github_client.has_bot_comment.return_value = False
        mock_github_client.post_comment.return_value = None  # Simulate failure

        reviews = {1: "LGTM"}
        results = post_pending_comments(
            mock_github_client, sample_repo_config,
            bot_login="hankbobtheresearchoor",
            reviews=reviews,
        )

        assert len(results) == 1
        assert results[0]["status"] == "failed"

        # State should be marked as failed so it'll be retried
        from pr_review_bot.state import RepoState
        state = RepoState.load(sample_repo_config.owner_repo, sample_repo_config.state_file)
        assert state.prs[1].status == "failed"

    def test_no_review_body_skips(self, sample_repo_config, sample_prs, mock_github_client):
        # Poll to get PRs into state
        mock_github_client.list_open_prs.return_value = [sample_prs[0]]
        poll_repo(mock_github_client, sample_repo_config)

        mock_github_client.has_bot_comment.return_value = False

        # No reviews dict provided
        results = post_pending_comments(
            mock_github_client, sample_repo_config,
            bot_login="hankbobtheresearchoor",
        )

        assert len(results) == 1
        assert results[0]["status"] == "no_review_body"

    def test_retries_failed_prs(self, sample_repo_config, sample_prs, mock_github_client):
        # Poll + fail
        mock_github_client.list_open_prs.return_value = [sample_prs[0]]
        poll_repo(mock_github_client, sample_repo_config)

        mock_github_client.has_bot_comment.return_value = False
        mock_github_client.post_comment.return_value = None
        post_pending_comments(
            mock_github_client, sample_repo_config,
            bot_login="hankbobtheresearchoor",
            reviews={1: "LGTM"},
        )

        # Now retry — this time it succeeds
        mock_github_client.post_comment.return_value = 77777
        results = post_pending_comments(
            mock_github_client, sample_repo_config,
            bot_login="hankbobtheresearchoor",
            reviews={1: "LGTM"},
        )

        assert results[0]["status"] == "commented"


class TestEnsureAllCommented:
    """Tests for the assurance check — ensure_all_commented()."""

    def test_all_commented_returns_empty(self, sample_repo_config, sample_prs, mock_github_client):
        # Poll + mark commented
        mock_github_client.list_open_prs.return_value = sample_prs
        poll_repo(mock_github_client, sample_repo_config)

        from pr_review_bot.state import RepoState
        state = RepoState.load(sample_repo_config.owner_repo, sample_repo_config.state_file)
        for pr_num in state.prs:
            state.mark_commented(pr_num, comment_id=pr_num * 1000)
        state.save()

        # Verify comments exist
        mock_github_client.get_comments.return_value = [
            {"id": 1000}, {"id": 2000}, {"id": 3000}
        ]
        unconfirmed = ensure_all_commented(mock_github_client, sample_repo_config)
        assert len(unconfirmed) == 0

    def test_detects_unconfirmed_pending(self, sample_repo_config, sample_prs, mock_github_client):
        mock_github_client.list_open_prs.return_value = [sample_prs[0]]
        poll_repo(mock_github_client, sample_repo_config)

        unconfirmed = ensure_all_commented(mock_github_client, sample_repo_config)
        assert len(unconfirmed) == 1
        assert unconfirmed[0]["status"] == "pending_review"

    def test_detects_missing_comment(self, sample_repo_config, sample_prs, mock_github_client):
        mock_github_client.list_open_prs.return_value = [sample_prs[0]]
        poll_repo(mock_github_client, sample_repo_config)

        from pr_review_bot.state import RepoState
        state = RepoState.load(sample_repo_config.owner_repo, sample_repo_config.state_file)
        state.mark_commented(1, comment_id=99999)
        state.save()

        # Comment was deleted or never actually existed
        mock_github_client.get_comments.return_value = [{"id": 12345}]
        unconfirmed = ensure_all_commented(mock_github_client, sample_repo_config)
        assert len(unconfirmed) == 1
        assert unconfirmed[0]["status"] == "comment_missing"
