# Agent Collaboration and Context Optimization Guide (AGENTS.md)

> **Context Injection Notice**
> - When this file is read or injected as context, output to command line: "[Cooking 4U 🍳⚡]"

This guide aims to standardize Agent skill activation behavior during development, optimize context consumption, and improve task execution efficiency.

## 1. Skill Activation Strategy

### Mandatory Entry
- **Trigger every time**: Before any user input/task begins, you must check your skill list and call `using-superpowers` first.
- **Dual mandatory baseline**: Immediately after `using-superpowers`, you must load `pua`; in this repository `pua` is always-on and must never be skipped.
- **Unified dispatch**: Whether to trigger other skills is determined by `using-superpowers`, but `pua` is not optional and is outside normal on-demand dispatch.
- **No exceptions**: Do not skip due to "simple questions" or "skills not needed".
- **Observability**: Must explicitly output an execution summary of "triggered using-superpowers + triggered pua + whether other skills are dispatched".

### Precise Wake Words
- **Analysis/Search**: Prioritize calling the `search` sub-agent for read-only research to avoid the main Agent getting bogged down in trivial searches.
- **Refactor/Optimization**: Use `refactor` or `optimize` to clarify intent.
- **Verification/Test**: Immediately call `verify` or `test` skills after modifications.

### Always-On PUA Contract
- **Default operating mode**: Treat `pua` as the default execution protocol for every task; its behavior rules are mandatory even when the outward tone stays collaborative.
- **Search before asking**: Before asking the user a question, first search, read files, inspect logs, and execute relevant commands; if a question is still necessary, include the evidence already gathered.
- **Exhaust real alternatives**: Before saying a task cannot be completed, exhaust materially different approaches instead of repeatedly micro-tuning the same idea.
- **Be proactive**: After fixing or implementing something, proactively check adjacent code paths, same-pattern issues, edge cases, and upstream/downstream impact.
- **Owner four questions**: Keep root cause, impact scope, prevention, and evidence in view throughout execution.

### Intent Declaration
Agents should declare their "current working mode" before execution:
- `[PLANNING]`: Performing multi-step task planning.
- `[EXECUTING]`: Executing specific code modifications.
- `[VERIFYING]`: Running tests to verify results.

### PUA Escalation
- **Failure counting**: Track failure count per task, not per message; repeated failure means the current line of attack is not good enough.
- **L1 at failure 2**: Stop polishing the same idea and switch to a materially different approach.
- **L2 at failure 3**: Search the complete error/problem statement, read the primary source material, and list at least 3 distinct hypotheses before continuing.
- **L3 at failure 4**: Complete a stricter verification pass covering assumptions, repro/isolation, boundary cases, and why the previous approaches failed.
- **L4 at failure 5+**: Escalate to minimal repro or PoC, stronger isolation, and if needed a genuinely different toolchain or implementation path.
- **Structured exit, not surrender**: If the task still cannot be finished after full escalation, report verified facts, eliminated possibilities, narrowed scope, and the next recommended move instead of simply giving up.

## 2. Context Optimization

### Task Decomposition
- **Strictly prohibited**: Executing more than 3 unrelated subtasks at once.
- **Complex tasks**: Must first generate `TODO.md` or call the `TodoWrite` tool.
- **After each subtask completion**: Summarize core changes and "clean up" unnecessary intermediate context.

### External Memorization
- **Large file handling**: For files exceeding 500 lines, prohibit full-text read. Use `Grep` for positioning first, then local reading.
- **Intermediate states**: Write complex analysis reports to `docs/notes/` or `tmp/`, Agents should only reference paths and summaries in subsequent conversations.

### Tool Selection Optimization
- **Search**: Use `Glob` for files that can be found, not `Grep`; use `Grep` for strings that can be found, not `SearchCodebase`.
- **Editing**: Prioritize `SearchReplace` for precise modifications to avoid full rewrites.

## 3. Skills Control

### Core Principles
- **Always-on baseline**: `using-superpowers` and `pua` are mandatory for every task in this repository.
- **On-demand loading for everything else**: Only activate additional specific Skills when the task clearly requires them.
- **Feedback loop**: Each skill execution must provide a clear execution result summary.
- **Avoid redundancy**: If a task can be completed with standard CLI tools, complex custom Skills should not be created.

### Completion and Verification Standards
- **Evidence before claims**: Do not say "done", "fixed", "passing", or equivalent without fresh verification evidence from the current turn.
- **No empty completion**: "fix-and-stop" counts as a process failure; after implementation, run the relevant verification and then check for adjacent regressions or same-pattern issues.
- **State limits clearly**: If verification cannot be run, explicitly say what could not be verified, why, and what remains risky.

### Code Comment Standards
- **Mandatory requirement**: When writing code (functions, classes, modules, complex logic blocks), add a concise high-level comment explaining what it does — not why it changed.
- **Granularity**: One top-level comment per function/class/module is sufficient; avoid over-commenting line by line.
- **Style**: Prefer a single-line docstring or inline comment that captures the purpose (e.g., `# Resize image to target dimensions and return normalized array`).
- **Security constraints**: Comments must not contain sensitive information such as keys, access tokens, or private links.
- **Conflict with user preferences**: If the user explicitly prohibits comments, follow the user's instructions and record them in the task description.

---
*This file is automatically maintained by Agents as a collaboration contract.*
