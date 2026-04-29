"""PR poller — detects new PRs across whitelisted repos."""

from __future__ import annotations

import json
import sys
from typing import Any

from .config import BotConfig, RepoConfig
from .github_client import GitHubClient
from .state import RepoState


def poll_repo(client: GitHubClient, repo_cfg: RepoConfig) -> list[dict[str, Any]]:
    """Poll a single repo for new PRs. Returns list of new PR metadata dicts."""
    state = RepoState.load(repo_cfg.owner_repo, repo_cfg.state_file)
    open_prs = client.list_open_prs(repo_cfg.owner_repo)

    if not open_prs:
        return []

    new_numbers = state.unseen_prs([p.number for p in open_prs])
    if not new_numbers:
        return []

    new_prs = [p for p in open_prs if p.number in new_numbers]
    results = []

    for pr in new_prs:
        rec = state.mark_seen(pr.number, pr.title, pr.author)
        results.append({
            "repo": repo_cfg.owner_repo,
            "number": pr.number,
            "title": pr.title,
            "author": pr.author,
            "branch": pr.branch,
            "url": pr.url,
            "head_sha": pr.head_sha,
            "status": rec.status,
        })

    state.save()
    return results


def poll_all(config: BotConfig | None = None) -> list[dict[str, Any]]:
    """Poll all whitelisted repos. Returns combined list of new PRs."""
    if config is None:
        config = BotConfig.from_env()

    client = GitHubClient(github_token=config.github_token)
    all_new: list[dict[str, Any]] = []

    for repo_cfg in config.repos:
        try:
            new = poll_repo(client, repo_cfg)
            all_new.extend(new)
        except Exception as e:
            print(f"Error polling {repo_cfg.owner_repo}: {e}", file=sys.stderr)

    return all_new


def main() -> None:
    """CLI entry point — polls repos and prints new PRs as JSON lines."""
    try:
        config = BotConfig.from_env()
    except ValueError as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)

    new_prs = poll_all(config)
    if not new_prs:
        return  # No output = nothing to process

    print(f"Found {len(new_prs)} new PR(s):")
    for pr in new_prs:
        print(json.dumps(pr))


if __name__ == "__main__":
    main()
