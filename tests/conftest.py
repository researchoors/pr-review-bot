"""Shared test fixtures and helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pr_review_bot.config import BotConfig, RepoConfig
from pr_review_bot.github_client import PRInfo


@pytest.fixture
def tmp_state_dir(tmp_path):
    """Temporary directory for state files."""
    return tmp_path / "state"


@pytest.fixture
def sample_repo_config(tmp_state_dir):
    """A single repo config pointing to temp state."""
    tmp_state_dir.mkdir(parents=True, exist_ok=True)
    return RepoConfig(
        owner_repo="TestOrg/test-repo",
        state_file=tmp_state_dir / "TestOrg--test-repo.json",
        github_token="fake-token",
    )


@pytest.fixture
def multi_repo_config(tmp_state_dir):
    """Config with multiple repos."""
    tmp_state_dir.mkdir(parents=True, exist_ok=True)
    return BotConfig(
        repos=[
            RepoConfig(
                owner_repo="OrgA/repo-a",
                state_file=tmp_state_dir / "OrgA--repo-a.json",
                github_token="fake-token",
            ),
            RepoConfig(
                owner_repo="OrgB/repo-b",
                state_file=tmp_state_dir / "OrgB--repo-b.json",
                github_token="fake-token",
            ),
        ],
        default_state_dir=tmp_state_dir,
        github_token="fake-token",
    )


@pytest.fixture
def sample_prs():
    """Sample PR data for testing."""
    return [
        PRInfo(
            number=1,
            title="Fix bug in auth",
            author="dev1",
            branch="fix/auth",
            url="https://github.com/TestOrg/test-repo/pull/1",
            created_at="2026-04-29T00:00:00Z",
            updated_at="2026-04-29T00:00:00Z",
            head_sha="abc123",
            state="open",
        ),
        PRInfo(
            number=2,
            title="Add new feature",
            author="dev2",
            branch="feat/new",
            url="https://github.com/TestOrg/test-repo/pull/2",
            created_at="2026-04-29T01:00:00Z",
            updated_at="2026-04-29T01:00:00Z",
            head_sha="def456",
            state="open",
        ),
        PRInfo(
            number=3,
            title="Update dependencies",
            author="dependabot[bot]",
            branch="dependabot/deps",
            url="https://github.com/TestOrg/test-repo/pull/3",
            created_at="2026-04-29T02:00:00Z",
            updated_at="2026-04-29T02:00:00Z",
            head_sha="ghi789",
            state="open",
        ),
    ]


@pytest.fixture
def mock_github_client():
    """A mock GitHubClient that can be configured per test."""
    client = MagicMock()
    client._token = "fake-token"
    return client
