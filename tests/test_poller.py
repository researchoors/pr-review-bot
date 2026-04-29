"""Tests for the poller module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from pr_review_bot.config import BotConfig, RepoConfig
from pr_review_bot.github_client import PRInfo
from pr_review_bot.poller import poll_all, poll_repo


class TestPollRepo:
    """Tests for poll_repo()."""

    def test_detects_new_prs(self, sample_repo_config, sample_prs, mock_github_client):
        mock_github_client.list_open_prs.return_value = sample_prs
        new = poll_repo(mock_github_client, sample_repo_config)

        assert len(new) == 3
        assert new[0]["number"] == 1
        assert new[0]["repo"] == "TestOrg/test-repo"
        assert new[0]["status"] == "pending_review"

    def test_skips_already_seen_prs(self, sample_repo_config, sample_prs, mock_github_client):
        # First poll sees all 3
        mock_github_client.list_open_prs.return_value = sample_prs
        poll_repo(mock_github_client, sample_repo_config)

        # Second poll with same PRs should return nothing
        new = poll_repo(mock_github_client, sample_repo_config)
        assert len(new) == 0

    def test_detects_only_new_prs(self, sample_repo_config, sample_prs, mock_github_client):
        # First poll
        mock_github_client.list_open_prs.return_value = sample_prs
        poll_repo(mock_github_client, sample_repo_config)

        # Add a new PR
        new_pr = PRInfo(
            number=4, title="New PR", author="dev3", branch="feat/x",
            url="https://github.com/TestOrg/test-repo/pull/4",
            created_at="2026-04-29T03:00:00Z", updated_at="2026-04-29T03:00:00Z",
            head_sha="jkl012", state="open",
        )
        mock_github_client.list_open_prs.return_value = sample_prs + [new_pr]
        new = poll_repo(mock_github_client, sample_repo_config)
        assert len(new) == 1
        assert new[0]["number"] == 4

    def test_empty_repo(self, sample_repo_config, mock_github_client):
        mock_github_client.list_open_prs.return_value = []
        new = poll_repo(mock_github_client, sample_repo_config)
        assert len(new) == 0

    def test_api_failure(self, sample_repo_config, mock_github_client):
        mock_github_client.list_open_prs.return_value = []  # API failure returns empty
        new = poll_repo(mock_github_client, sample_repo_config)
        assert len(new) == 0

    def test_state_persists_to_disk(self, sample_repo_config, sample_prs, mock_github_client):
        mock_github_client.list_open_prs.return_value = sample_prs
        poll_repo(mock_github_client, sample_repo_config)

        # Verify state file was written
        assert sample_repo_config.state_file.exists()
        data = json.loads(sample_repo_config.state_file.read_text())
        assert "1" in data["prs"]
        assert "2" in data["prs"]
        assert "3" in data["prs"]


class TestPollAll:
    """Tests for poll_all() with multiple repos."""

    def test_polls_all_repos(self, multi_repo_config, mock_github_client):
        prs_a = [
            PRInfo(number=1, title="PR A1", author="dev", branch="a1",
                   url="http://example.com/1", created_at="", updated_at="",
                   head_sha="aaa", state="open"),
        ]
        prs_b = [
            PRInfo(number=10, title="PR B1", author="dev", branch="b1",
                   url="http://example.com/10", created_at="", updated_at="",
                   head_sha="bbb", state="open"),
        ]

        def mock_list_prs(repo):
            if repo == "OrgA/repo-a":
                return prs_a
            elif repo == "OrgB/repo-b":
                return prs_b
            return []

        mock_github_client.list_open_prs.side_effect = mock_list_prs
        with patch("pr_review_bot.poller.GitHubClient", return_value=mock_github_client):
            new = poll_all(multi_repo_config)

        assert len(new) == 2
        repos_seen = [r["repo"] for r in new]
        assert "OrgA/repo-a" in repos_seen
        assert "OrgB/repo-b" in repos_seen

    def test_continues_on_repo_error(self, multi_repo_config, mock_github_client):
        def mock_list_prs(repo):
            if repo == "OrgA/repo-a":
                raise ConnectionError("API down")
            return [
                PRInfo(number=10, title="PR B1", author="dev", branch="b1",
                       url="http://example.com/10", created_at="", updated_at="",
                       head_sha="bbb", state="open"),
            ]

        mock_github_client.list_open_prs.side_effect = mock_list_prs
        with patch("pr_review_bot.poller.GitHubClient", return_value=mock_github_client):
            new = poll_all(multi_repo_config)

        # Should still get results from OrgB
        assert len(new) == 1
        assert new[0]["repo"] == "OrgB/repo-b"
