"""Tests for dynamic repo whitelisting and config."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pr_review_bot.config import BotConfig, RepoConfig


class TestBotConfig:
    """Tests for BotConfig.from_env()."""

    def test_single_repo(self, monkeypatch):
        monkeypatch.setenv("PR_REVIEW_REPOS", "Layr-Labs/d-inference")
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
        config = BotConfig.from_env()
        assert len(config.repos) == 1
        assert config.repos[0].owner_repo == "Layr-Labs/d-inference"
        assert config.github_token == "ghp_test123"

    def test_multiple_repos(self, monkeypatch):
        monkeypatch.setenv("PR_REVIEW_REPOS", "OrgA/repo-a, OrgB/repo-b,OrgC/repo-c")
        config = BotConfig.from_env()
        assert len(config.repos) == 3
        assert config.repos[0].owner_repo == "OrgA/repo-a"
        assert config.repos[1].owner_repo == "OrgB/repo-b"
        assert config.repos[2].owner_repo == "OrgC/repo-c"

    def test_state_file_paths(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PR_REVIEW_REPOS", "Layr-Labs/d-inference")
        monkeypatch.setenv("PR_REVIEW_STATE_DIR", str(tmp_path))
        config = BotConfig.from_env()
        assert config.repos[0].state_file == tmp_path / "Layr-Labs--d-inference.json"

    def test_custom_poll_interval(self, monkeypatch):
        monkeypatch.setenv("PR_REVIEW_REPOS", "Org/repo")
        monkeypatch.setenv("PR_REVIEW_POLL_SECS", "30")
        config = BotConfig.from_env()
        assert config.poll_interval_seconds == 30

    def test_missing_env_var_raises(self, monkeypatch):
        monkeypatch.delenv("PR_REVIEW_REPOS", raising=False)
        with pytest.raises(ValueError, match="PR_REVIEW_REPOS"):
            BotConfig.from_env()

    def test_empty_env_var_raises(self, monkeypatch):
        monkeypatch.setenv("PR_REVIEW_REPOS", "  ,  ,  ")
        with pytest.raises(ValueError, match="PR_REVIEW_REPOS"):
            BotConfig.from_env()

    def test_no_token(self, monkeypatch):
        monkeypatch.setenv("PR_REVIEW_REPOS", "Org/repo")
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        config = BotConfig.from_env()
        assert config.github_token is None

    def test_whitespace_handling(self, monkeypatch):
        monkeypatch.setenv("PR_REVIEW_REPOS", "  Org/repo  ,  Other/repo2  ")
        config = BotConfig.from_env()
        assert len(config.repos) == 2
        assert config.repos[0].owner_repo == "Org/repo"
        assert config.repos[1].owner_repo == "Other/repo2"
