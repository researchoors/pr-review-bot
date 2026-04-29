"""Configuration — repo whitelisting, state file paths, GitHub auth."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RepoConfig:
    """Configuration for a single watched repository."""

    owner_repo: str  # e.g. "Layr-Labs/d-inference"
    state_file: Path
    github_token: str | None = None


@dataclass
class BotConfig:
    """Top-level bot configuration, loaded from environment."""

    repos: list[RepoConfig] = field(default_factory=list)
    default_state_dir: Path = field(default_factory=lambda: Path.home() / ".pr-review-bot")
    github_token: str | None = None
    poll_interval_seconds: int = 60

    @classmethod
    def from_env(cls) -> BotConfig:
        """Load configuration from environment variables.

        Env vars:
            PR_REVIEW_REPOS      — comma-separated owner/repo list (required)
            PR_REVIEW_STATE_DIR  — directory for state files (default: ~/.pr-review-bot)
            GITHUB_TOKEN         — GitHub personal access token
            PR_REVIEW_POLL_SECS  — poll interval in seconds (default: 60)
        """
        repos_str = os.environ.get("PR_REVIEW_REPOS", "")
        if not repos_str.strip():
            raise ValueError("PR_REVIEW_REPOS env var is required (comma-separated owner/repo list)")

        repo_names = [r.strip() for r in repos_str.split(",") if r.strip()]
        if not repo_names:
            raise ValueError("PR_REVIEW_REPOS env var is required (comma-separated owner/repo list)")
        state_dir = Path(os.environ.get("PR_REVIEW_STATE_DIR", str(Path.home() / ".pr-review-bot")))
        token = os.environ.get("GITHUB_TOKEN")
        poll_secs = int(os.environ.get("PR_REVIEW_POLL_SECS", "60"))

        repos = []
        for name in repo_names:
            safe_name = name.replace("/", "--")
            repos.append(RepoConfig(
                owner_repo=name,
                state_file=state_dir / f"{safe_name}.json",
                github_token=token,
            ))

        return cls(
            repos=repos,
            default_state_dir=state_dir,
            github_token=token,
            poll_interval_seconds=poll_secs,
        )
