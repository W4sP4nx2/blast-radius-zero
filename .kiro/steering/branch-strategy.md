# Branch Strategy Framework

## Branch Types

| Branch Type | Naming Convention | Purpose & Lifetime | Push / Merge Criteria |
|---|---|---|---|
| Production / Stable | `main` | Production-ready source of truth. Always compilable and clean. | Requires passing test suite, no raw session logs, clean rebased history. |
| Feature / Component | `feat/<module-name>` | Isolated sandbox or core architecture work (e.g., `feat/mcp-server`, `feat/sandbox-isolation`). | Merged into `main` after passing automated/local unit tests. |
| Workspace / Agent Session | `agent/<session-id-or-task>` | Short-lived environment for running concurrent workspace agent sessions via withnative/native. | Ephemeral. Cherry-pick clean code changes to `feat/*`, then discard raw session branches. |
| Hotfix | `hotfix/<issue>` | Rapid fixes for broken isolation boundaries or critical state bugs. | Direct PR to `main` with immediate version bump. |

## Decision Matrix: When to Update `main` vs. Branches

```
                     Is this a raw multi-agent session output?
                                     │
                    ┌────────────────┴────────────────┐
                   NO                                YES
                    │                                 │
     Is the feature stable and tested?       Keep on `agent/*` branch
                    │                        or discard after state export.
          ┌─────────┴─────────┐
         YES                 NO
          │                   │
  Merge into `main`     Keep on `feat/*`
  via Squash & Merge.   branch for refinement.
```

## Merging Guidelines: When to Merge into `main`

These rules keep `main` stable while custom features are iterated on.

| Branch Type | Merge Condition | Push / Commit Strategy |
|---|---|---|
| Feature Branch (`feat/*`) | Merge into `main` only after the local policy engine unit tests pass and documentation is updated. | Use Squash and Merge to keep the `main` commit history clean. |
| Agent / Session Branch (`agent/*`) | Do not merge directly to `main`. Pick stable code snippets onto a `feat/*` branch, then discard the temporary session branch. | Delete the branch after extracting clean code logic. |
| Main Branch (`main`) | Always kept in a clean, runnable, starter-ready state. | Never push raw unverified work directly to `main`. |

Local checks before merging a `feat/*` branch:

```bash
# Policy engine unit tests (required by the merge condition above)
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_policy.py -q

# Full application suite, as run by CI
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -m 'not integration' --fail-on-skip -q
```

CI also runs these tests and Python Docker containment on every PR targeting `main` (see `TESTING.md`).

## Syncing a Branch with `origin/main` (Pull & Commit Fixes)

Use this sequence when a pull or commit is blocked by local changes or a stale branch. It keeps uncommitted work instead of deleting it.

1. **Isolate local changes:** `git stash -u`. Verify with `git status` that the working tree is clean.
2. **Sync remote changes via rebase:** `git fetch origin`, then `git rebase origin/main`. Verify with `git log --oneline -n 5` that your commits sit on top of the latest `main` commit.
3. **Re-apply stashed work:** `git stash pop`. Verify with `git status` that your modified files are restored.
4. **Update ignore rules:** if caches or session artifacts show up in `git status`, add their patterns to `.gitignore` (see [Ignored Local State](#ignored-local-state)). Verify by running the tests, then `git status`; the caches should not be listed.

Notes:

- Edit `.gitignore` after step 3, or commit the edit before step 2. `git rebase` refuses to start with unstaged changes, and an uncommitted `.gitignore` edit can conflict with `git stash pop`.
- `.gitignore` only affects untracked files. To stop tracking a file that is already committed, run `git rm --cached <path>` and commit the removal.
- If `git stash pop` reports a conflict, git keeps the stash. Resolve the conflict, then run `git stash drop`.
- Rebasing a branch that is already pushed rewrites its history, and pushing it again needs `git push --force-with-lease`. Get explicit approval before force-pushing a shared branch.

## Repository Cleanup Protocol

Run this command sequence in your local shell to scrub the repository state:

```bash
# 1. Clean untracked files, local caches, and temporary artifacts (-d directories, -f force, -x ignored files optional)
git clean -fd

# 2. Rebase active feature branch onto latest origin/main
git fetch origin
git rebase origin/main

# 3. Prune local references to deleted remote branches
git remote prune origin

# 4. Remove local merged branches (except main)
git branch --merged main | grep -v '^\*' | grep -v 'main' | xargs -r git branch -d
```

Notes:

- `git clean -fd` permanently deletes untracked files, including new work that was never committed. Preview with `git clean -nd` first, or use `git stash -u` from the sync sequence above.
- Squash-merged branches do not appear in `git branch --merged main`, so step 4 skips them. After the PR shows as merged, delete the local branch with `git branch -D <branch>`.

## Ignored Local State

The repository `.gitignore` covers these patterns:

```gitignore
# Agent Workspace Runtime Caches & Local State
.native/
*.session.json
logs/
/tmp/

# Python & Environment
__pycache__/
*.pyc
.venv/
.pytest_cache/

# System Files
.DS_Store
```
