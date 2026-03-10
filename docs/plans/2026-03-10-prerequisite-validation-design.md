# Python Dev Bundle Prerequisite Validation Design

## Goal

Ensure the `amplifier-bundle-python-dev` bundle clearly signals when prerequisite tools (`ruff`, `pyright`) are not installed, rather than silently returning clean results.

## Background

The bundle invokes `ruff` and `pyright` via `sys.executable -m <tool>` in subprocess calls. When these Python packages aren't installed, `subprocess.run()` returns non-zero with `"No module named 'ruff'"` on stderr — but the existing error handling only catches `FileNotFoundError`, which is never raised in this case. The code proceeds to parse empty stdout and returns a clean `CheckResult`. Users get no signal that their environment is misconfigured.

This is a particularly insidious failure mode: the bundle appears to work, checks appear to pass, and the user has false confidence that their code has been validated.

The `browser-tester` and `terminal-tester` bundles in the Amplifier ecosystem have already solved equivalent problems — prerequisite tools that must be present for the bundle to function. This design follows their established patterns exactly, adapted for the python-dev bundle's specific tools and invocation model.

## Approach

**"Tester Bundle Pattern"** — follow exactly what `browser-tester` and `terminal-tester` do, adapted for `python-dev`. No novel patterns invented.

The fix is applied at four layers, providing defense in depth:

1. **Bug fix** — `checker.py` stops returning false clean results when tools are missing
2. **Context awareness** — the orchestrating agent knows about prerequisites from turn 1
3. **Agent self-check** — the quality-checking agent verifies tools before first use
4. **Hook surface** — even if the agent skips its check, file-save hooks surface the problem visually

Key decisions:
- Check tools as Python modules first (`python -m ruff --version`); use PATH check (`which ruff`) only as a diagnostic hint if it helps guide resolution
- Both agent self-check AND hook-level handling — belt and suspenders
- The silent-success bug fix is included as part of this work since it's the root cause

## Architecture

```
User saves .py file
        │
        ▼
┌─────────────────────┐
│  Hook (on_save)     │──── Layer 4: TOOL-NOT-FOUND → distinct user_message
│  __init__.py        │     (backstop for sub-agents without full instructions)
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  checker.py         │──── Layer 1: Bug fix — detect "No module named" on stderr
│  _run_ruff_format   │     Return TOOL-NOT-FOUND instead of silent clean result
│  _run_ruff_lint     │
│  _run_pyright       │
└─────────────────────┘

Agent receives task
        │
        ▼
┌─────────────────────┐
│  python-dev.md      │──── Layer 3: Self-check block before first python_check call
│  (agent)            │     Runs: python -m ruff --version && python -m pyright --version
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│  python-dev-        │──── Layer 2: Context awareness — prerequisites + troubleshooting
│  instructions.md    │     Loaded into every session via python-quality.yaml
└─────────────────────┘
```

## Components

### Component 1: Bug Fix — Silent Success in `checker.py`

**File:** `src/amplifier_bundle_python_dev/checker.py`

**Problem:** `_run_ruff_format`, `_run_ruff_lint`, and `_run_pyright` invoke tools via `sys.executable -m ruff` (etc.) and catch `FileNotFoundError`. But when the Python module isn't installed, subprocess returns non-zero with `"No module named 'ruff'"` on stderr — `FileNotFoundError` is never raised. The code then parses empty stdout and returns a clean `CheckResult`.

**Fix:** In each of the three `_run_*` methods, after the `subprocess.run()` call, add an early-return check:

- If `result.returncode != 0` and stderr contains `"No module named"`, return the same `TOOL-NOT-FOUND` `CheckResult` that the existing `FileNotFoundError` handler returns
- Keep the existing `except FileNotFoundError` as a safety net (covers the edge case where `sys.executable` itself is missing)
- Use the same error messages already defined:
  - `"ruff not found. Install with: uv add ruff"`
  - `"pyright not found. Install with: uv add pyright"`

**Scope:** Three methods in one file. A few lines of early-return logic in each method, right after the `subprocess.run()` call. No new files, no new dependencies.

### Component 2: Context Awareness File — Prerequisites + Troubleshooting

**File:** `context/python-dev-instructions.md`

**Pattern source:** Directly mirrors `browser-tester:context/browser-awareness.md` and `terminal-tester:context/terminal-awareness.md`.

Add two new sections to the existing context file (which is already loaded into every session via `behaviors/python-quality.yaml`):

**Prerequisites section:**
- `ruff` and `pyright` must be installed as Python packages in the active environment
- Verification command: `python -m ruff --version && python -m pyright --version`
- Install command: `uv add ruff pyright` (or `pip install ruff pyright`)
- Brief explanation of why they need to be Python modules (the bundle invokes them via `sys.executable -m`)

**Troubleshooting table mapping symptoms to fixes:**

| Symptom | Fix |
|---|---|
| `TOOL-NOT-FOUND: ruff not found` | `uv add ruff` |
| `TOOL-NOT-FOUND: pyright not found` | `uv add pyright` |
| Checks return no issues but ruff isn't running | Verify with `python -m ruff --version` |
| `pyright-langserver` not found (LSP side) | `npm install -g pyright` |

This is the "doctor-by-awareness" pattern the ecosystem uses: the context file loads into the root session, so the orchestrating agent is aware of prerequisites from turn 1 — even before any tool is invoked.

**Scope:** Additions to one existing file. No new files.

### Component 3: Agent Self-Check Blocks

**File:** `agents/python-dev.md`

**Pattern source:** Directly mirrors `browser-tester:agents/browser-operator.md` (lines 45–61) and `terminal-tester:agents/terminal-operator.md` (lines 59–67).

Add a `## Prerequisites Self-Check (REQUIRED)` section placed before the core workflow instructions:

- Before the first `python_check` call in every session, verify the tools are available
- Run: `python -m ruff --version` and `python -m pyright --version`
- If either fails with `"No module named"`, tell the user the install command (`uv add ruff pyright`) and stop — do not attempt checks without the tools
- If the command succeeds on PATH (`which ruff`) but not as a module, explain that the tools must be installed in the active Python environment

**Graduated specificity** (following `terminal-tester`'s pattern): The primary agent (`python-dev.md`) gets the full check. The specialist agent (`code-intel.md`) checks only its own dependency (`pyright-langserver`), which it already does — no changes needed to `code-intel.md`.

**Scope:** Additions to one agent file.

### Component 4: Improved Hook Surface for TOOL-NOT-FOUND

**File:** `modules/hooks-python-check/amplifier_module_hooks_python_check/__init__.py`

**Current behavior:** The hook calls `check_files()`, gets back issues, formats them generically, and injects them as context. A `TOOL-NOT-FOUND` error looks like just another issue in the list — and after the first occurrence on a given file, the redundancy suppression logic silences it on subsequent saves.

**New behavior:** After getting the `CheckResult` back from the checker, check if any issues have `code == "TOOL-NOT-FOUND"`. If so:

- Return a `HookResult` with a distinct `user_message` like: `"⚠ Python dev tools not installed: ruff not found. Install with: uv add ruff"`
- Use `user_message_level="error"` so it's visually prominent
- Skip the normal issue-formatting path for these — they're not code quality issues, they're setup issues
- Don't apply redundancy suppression to these — the user should see this every time until they fix it (or at least on the first save per session)

This ensures that even if the agent skips its self-check (e.g., a sub-agent spawned without the full agent instructions), the hook provides a backstop. The first time someone edits a `.py` file, they'll get a clear signal that tools are missing.

**Scope:** Logic changes in one file. No new files or dependencies.

## Data Flow

### Happy Path (tools installed)

1. User saves `.py` file → hook fires → `checker.py` runs `sys.executable -m ruff ...` → ruff executes → issues parsed and returned → hook formats and displays
2. Agent receives task → self-check passes (`python -m ruff --version` succeeds) → proceeds to `python_check` → normal workflow

### Unhappy Path (tools missing)

1. **Hook path:** User saves `.py` file → hook fires → `checker.py` runs `sys.executable -m ruff ...` → subprocess returns non-zero, stderr contains `"No module named"` → **new early-return** produces `TOOL-NOT-FOUND` `CheckResult` → hook detects `TOOL-NOT-FOUND` → returns `HookResult` with `user_message_level="error"` and install instructions
2. **Agent path:** Agent receives task → self-check runs `python -m ruff --version` → fails → agent tells user to run `uv add ruff pyright` → stops without attempting checks
3. **Context path:** Even before any tool invocation, the orchestrating agent has the prerequisites section loaded and can proactively guide setup

## Error Handling

| Layer | Error Condition | Handling |
|---|---|---|
| `checker.py` | `subprocess` returns non-zero + stderr contains `"No module named"` | Return `TOOL-NOT-FOUND` `CheckResult` with install instructions |
| `checker.py` | `FileNotFoundError` from subprocess (e.g., `sys.executable` missing) | Existing handler — returns same `TOOL-NOT-FOUND` `CheckResult` (kept as safety net) |
| Hook | `CheckResult` contains issues with `code == "TOOL-NOT-FOUND"` | Return `HookResult` with `user_message_level="error"`, skip normal formatting, bypass redundancy suppression |
| Agent | `python -m ruff --version` fails | Report to user with install command, stop workflow |
| Agent | `which ruff` succeeds but `python -m ruff` fails | Explain that tools must be in the active Python environment, not just on PATH |

## Testing Strategy

**Component 1 (checker.py bug fix):**
- Unit test: mock `subprocess.run` to return non-zero with `"No module named 'ruff'"` on stderr → verify `TOOL-NOT-FOUND` `CheckResult` is returned
- Unit test: verify existing `FileNotFoundError` path still works
- Unit test: verify normal non-zero returncode (actual lint errors) is still parsed correctly (not falsely caught by the new check)

**Component 2 (context file):**
- Manual verification that the prerequisites and troubleshooting sections render correctly
- Verify the file is still loaded via `behaviors/python-quality.yaml`

**Component 3 (agent self-check):**
- Manual testing in a session without `ruff`/`pyright` installed — verify the agent stops and reports the install command
- Manual testing in a session with tools installed — verify the agent proceeds normally

**Component 4 (hook surface):**
- Unit test: provide a `CheckResult` containing `TOOL-NOT-FOUND` issues → verify `HookResult` has `user_message_level="error"` and the correct message
- Unit test: verify redundancy suppression is bypassed for `TOOL-NOT-FOUND`
- Unit test: verify normal issues still go through the existing formatting path

**End-to-end:**
- In a clean environment without `ruff`/`pyright`: save a `.py` file → verify the hook surfaces the error prominently; start the agent → verify it stops with install instructions
- Install the tools → verify everything works normally

## Files Changed

| File | Change Type | Description |
|---|---|---|
| `src/amplifier_bundle_python_dev/checker.py` | Bug fix | Add module-not-found detection in `_run_ruff_format`, `_run_ruff_lint`, `_run_pyright` |
| `context/python-dev-instructions.md` | Addition | Add Prerequisites section and Troubleshooting table |
| `agents/python-dev.md` | Addition | Add Prerequisites Self-Check block before core workflow |
| `modules/hooks-python-check/amplifier_module_hooks_python_check/__init__.py` | Enhancement | Add TOOL-NOT-FOUND special handling with distinct user messaging |

## Open Questions

None — all decisions have been made. The design follows established patterns from the Amplifier ecosystem with no novel invention required.
