"""Helpers for inspecting remote Git repositories without cloning them.

Used both by the API (to offer a branch picker before import) and by the
indexing worker (to resolve the real default branch instead of assuming
``main``, which breaks for the many repositories that still use ``master``).
"""

from __future__ import annotations

import re
import subprocess

from app.core.logging import get_logger

logger = get_logger(__name__)

# ls-remote is a cheap network round-trip, but still bound it.
_LS_REMOTE_TIMEOUT = 30


class GitRemoteError(RuntimeError):
    """Raised when a remote repository cannot be inspected."""


def normalize_clone_url(url: str, auth_token: str | None = None) -> str:
    """Return an HTTPS clone URL, optionally with an embedded auth token.

    SSH-style URLs (``git@host:org/repo.git``) are rewritten to HTTPS so the
    container does not need SSH keys configured.

    Args:
        url: Raw repository URL as supplied by the user.
        auth_token: Optional PAT to embed for private HTTPS repositories.

    Returns:
        A clone URL suitable for ``git`` commands.
    """
    clone_url = url.strip()

    ssh_match = re.match(r"git@([^:]+):(.+)", clone_url)
    if ssh_match:
        host, path = ssh_match.group(1), ssh_match.group(2)
        clone_url = f"https://{host}/{path}"

    if auth_token and clone_url.startswith("https://"):
        proto, rest = clone_url.split("://", 1)
        # Strip any credentials already present to avoid doubling them up.
        rest = rest.split("@", 1)[-1]
        clone_url = f"{proto}://{auth_token}@{rest}"

    return clone_url


def _run_ls_remote(args: list[str]) -> str:
    """Run ``git ls-remote`` with credential prompts disabled.

    Args:
        args: Arguments appended after ``git ls-remote``.

    Returns:
        Captured stdout.

    Raises:
        GitRemoteError: If git fails or times out.
    """
    try:
        result = subprocess.run(
            ["git", "ls-remote", *args],
            capture_output=True,
            text=True,
            timeout=_LS_REMOTE_TIMEOUT,
            # Never block waiting for interactive credentials.
            env={"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "echo", "PATH": "/usr/bin:/bin:/usr/local/bin"},
        )
    except subprocess.TimeoutExpired as exc:
        raise GitRemoteError("Timed out contacting the remote repository.") from exc

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        # Avoid leaking an embedded token back to the caller.
        stderr = re.sub(r"https://[^@/\s]+@", "https://", stderr)
        raise GitRemoteError(stderr or "Failed to contact the remote repository.")

    return result.stdout


def list_remote_branches(url: str, auth_token: str | None = None) -> list[str]:
    """List branch names available on a remote repository.

    Args:
        url: Repository URL.
        auth_token: Optional PAT for private repositories.

    Returns:
        Sorted list of branch names.

    Raises:
        GitRemoteError: If the remote cannot be reached.
    """
    out = _run_ls_remote(["--heads", normalize_clone_url(url, auth_token)])
    branches = [
        line.split("refs/heads/", 1)[1].strip()
        for line in out.splitlines()
        if "refs/heads/" in line
    ]
    return sorted(set(branches))


def get_default_branch(url: str, auth_token: str | None = None) -> str | None:
    """Return the remote's default branch (the target of its HEAD symref).

    Args:
        url: Repository URL.
        auth_token: Optional PAT for private repositories.

    Returns:
        Branch name, or None if it could not be determined.
    """
    try:
        out = _run_ls_remote(["--symref", normalize_clone_url(url, auth_token), "HEAD"])
    except GitRemoteError as exc:
        logger.warning("default_branch_lookup_failed", error=str(exc))
        return None

    for line in out.splitlines():
        if line.startswith("ref:") and "refs/heads/" in line:
            return line.split("refs/heads/", 1)[1].split()[0].strip()
    return None


def resolve_branch(
    url: str,
    requested: str | None,
    auth_token: str | None = None,
) -> str:
    """Resolve the branch to clone, falling back to the remote's default.

    Resolution order:
    1. ``requested`` if it exists on the remote.
    2. The remote's HEAD symref (its real default branch).
    3. ``main`` / ``master`` if present.

    Args:
        url: Repository URL.
        requested: Branch the caller asked for, or None for auto-detect.
        auth_token: Optional PAT for private repositories.

    Returns:
        A branch name that exists on the remote.

    Raises:
        GitRemoteError: If the remote has no branches, or the requested branch
            does not exist (the message lists what is available).
    """
    branches = list_remote_branches(url, auth_token)
    if not branches:
        raise GitRemoteError("The remote repository has no branches.")

    if requested:
        if requested in branches:
            return requested
        preview = ", ".join(branches[:10]) + ("…" if len(branches) > 10 else "")
        raise GitRemoteError(
            f"Branch '{requested}' does not exist on the remote. "
            f"Available branches: {preview}"
        )

    head = get_default_branch(url, auth_token)
    if head and head in branches:
        return head

    for candidate in ("main", "master"):
        if candidate in branches:
            return candidate

    return branches[0]
