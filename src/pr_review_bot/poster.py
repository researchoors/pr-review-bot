"""Comment poster — ensures review comments are always posted on PRs.

Guarantees:
1. A PR is never marked "commented" until the comment is confirmed via API
2. On failure, the PR is marked "failed" and will be retried on next poll
3. Duplicate comments are prevented by checking for existing bot comments first
"""

from __future__ import annotations

import json
import sys
from typing import Any

from .config import BotConfig, RepoConfig
from .github_client import GitHubClient
from .state import RepoState


def post_pending_comments(
    client: GitHubClient,
    repo_cfg: RepoConfig,
    bot_login: str = "hankbobtheresearchoor",
    reviews: dict[int, str] | None = None,
) -> list[dict[str, Any]]:
    """Post review comments for all PRs in pending/reviewed/failed state.

    Args:
        client: GitHub API client
        repo_cfg: Repo configuration + state file path
        bot_login: GitHub login to check for existing comments (dedup)
        reviews: Optional mapping of PR number -> review body text.
                 If not provided, only dedup checks are done (no new posts).

    Returns:
        List of result dicts with number, status, comment_id (if posted).
    """
    state = RepoState.load(repo_cfg.owner_repo, repo_cfg.state_file)
    pending = state.pending_reviews()
    results = []

    for rec in pending:
        # Dedup: check if bot already commented
        if client.has_bot_comment(repo_cfg.owner_repo, rec.number, bot_login):
            state.mark_commented(rec.number, comment_id=-1)  # -1 = existing comment found
            results.append({
                "repo": repo_cfg.owner_repo,
                "number": rec.number,
                "status": "already_commented",
            })
            continue

        # Need a review body to post
        if reviews is None or rec.number not in reviews:
            results.append({
                "repo": repo_cfg.owner_repo,
                "number": rec.number,
                "status": "no_review_body",
            })
            continue

        body = reviews[rec.number]
        comment_id = client.post_comment(repo_cfg.owner_repo, rec.number, body)

        if comment_id is not None:
            state.mark_commented(rec.number, comment_id)
            results.append({
                "repo": repo_cfg.owner_repo,
                "number": rec.number,
                "status": "commented",
                "comment_id": comment_id,
            })
        else:
            state.mark_failed(rec.number, "comment_post_failed")
            results.append({
                "repo": repo_cfg.owner_repo,
                "number": rec.number,
                "status": "failed",
                "error": "comment_post_failed",
            })

    state.save()
    return results


def ensure_all_commented(
    client: GitHubClient,
    repo_cfg: RepoConfig,
    bot_login: str = "hankbobtheresearchoor",
) -> list[dict[str, Any]]:
    """Verify that every seen PR has a bot comment. Returns unconfirmed PRs.

    This is the assurance check — run after polling + reviewing to confirm
    nothing was silently dropped.
    """
    state = RepoState.load(repo_cfg.owner_repo, repo_cfg.state_file)
    unconfirmed = []

    for rec in state.prs.values():
        if rec.status == "commented":
            # Verify the comment still exists
            if rec.comment_id and rec.comment_id > 0:
                comments = client.get_comments(repo_cfg.owner_repo, rec.number)
                found = any(c.get("id") == rec.comment_id for c in comments)
                if not found:
                    unconfirmed.append({
                        "repo": repo_cfg.owner_repo,
                        "number": rec.number,
                        "status": "comment_missing",
                        "comment_id": rec.comment_id,
                    })
        elif rec.status in ("pending_review", "reviewed", "failed"):
            unconfirmed.append({
                "repo": repo_cfg.owner_repo,
                "number": rec.number,
                "status": rec.status,
            })

    return unconfirmed


def main() -> None:
    """CLI entry point — post comments for pending reviews from stdin.

    Reads JSON lines from stdin: {"number": N, "body": "review text"}
    """
    try:
        config = BotConfig.from_env()
    except ValueError as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)

    # Read review bodies from stdin
    reviews: dict[int, str] = {}
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            reviews[data["number"]] = data["body"]
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Skipping invalid input: {e}", file=sys.stderr)

    client = GitHubClient(github_token=config.github_token)
    all_results = []

    for repo_cfg in config.repos:
        results = post_pending_comments(client, repo_cfg, reviews=reviews)
        all_results.extend(results)

    for r in all_results:
        print(json.dumps(r))


if __name__ == "__main__":
    main()
