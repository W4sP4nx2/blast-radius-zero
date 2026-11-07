# Parallel agent sessions

Integration branch: `feature/native-integration`. Agents never commit to `main` directly.

## Isolation

- Each parallel session works in its own worktree under `.worktrees/<lane>` on branch `feature/native-integration-<lane>`, created from `feature/native-integration`.
- Each lane owns a fixed set of paths. A lane edits only its own paths; changes to shared files (`backend/brz/api.py`, `backend/brz/config.py`, `.env.example`, `README.md`, `requirements*.txt`) go through the integration branch, one lane at a time.
- When a lane finishes, rebase it onto `feature/native-integration`, run the checks below, then fast-forward merge it into the integration branch.

## Lanes

| Lane | Owns |
| --- | --- |
| `backend` | `backend/brz/native_*.py`, `backend/tests/test_native.py`, `backend/Dockerfile.native` |
| `docs` | `docs/native-integration.md`, `NATIVE_*.md`, `QUICKSTART_NATIVE.md`, `examples/` |

## Cross-review

A change written by one model is reviewed by a different model before merging into the integration branch.

## Limits

Run at most four sessions at once to stay under account rate limits.

## Checks before merging a lane

```bash
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -m 'not integration'
```

Containment rules in `AGENTS.md` apply to every lane.
