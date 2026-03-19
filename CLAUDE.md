# Agent Collaboration and Context Optimization Guide (AGENTS.md)

> **Context Injection Notice**
> - When this file is read or injected as context, output to command line: "Following project rules"

This guide aims to standardize Agent skill activation behavior during development, optimize context consumption, and improve task execution efficiency.

## 1. Skill Activation Strategy

### Mandatory Entry
- **Trigger every time**: Before any user input/task begins, you must check your skill list and call `using-superpowers` first.
- **Unified dispatch**: Whether to trigger other skills is determined by `using-superpowers`.
- **No exceptions**: Do not skip due to "simple questions" or "skills not needed".
- **Observability**: Must explicitly output an execution summary of "triggered using-superpowers + whether other skills are dispatched".

### Precise Wake Words
- **Analysis/Search**: Prioritize calling the `search` sub-agent for read-only research to avoid the main Agent getting bogged down in trivial searches.
- **Refactor/Optimization**: Use `refactor` or `optimize` to clarify intent.
- **Verification/Test**: Immediately call `verify` or `test` skills after modifications.

### Intent Declaration
Agents should declare their "current working mode" before execution:
- `[PLANNING]`: Performing multi-step task planning.
- `[EXECUTING]`: Executing specific code modifications.
- `[VERIFYING]`: Running tests to verify results.

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
- **On-demand loading**: Only activate specific Skills when the task clearly requires them.
- **Feedback loop**: Each skill execution must provide a clear execution result summary.
- **Avoid redundancy**: If a task can be completed with standard CLI tools, complex custom Skills should not be created.

### Change Annotation Standards
- **Mandatory requirement**: After each modification to code, routing, configuration, or documentation, add a brief single-line comment at the modification site in `//...;...;...` style.
- **Comment forms**:
  - Code files: Use a one-line inline comment near the change, for example `// ignore macOS Finder metadata; any .DS_Store file anywhere in the repo; verify with git check-ignore -v .DS_Store`.
  - Document files: Use a one-line HTML comment near the adjusted paragraph, for example `<!-- ignore macOS Finder metadata; any .DS_Store file anywhere in the repo; verify with git check-ignore -v .DS_Store -->`.
- **Style**: Prefer one line by default; keep the three parts unlabeled unless labels genuinely improve clarity.
- **Security constraints**: Comments must not contain sensitive information such as keys, access tokens, or private links.
- **Conflict with user preferences**: If the user explicitly prohibits comments, follow the user's instructions and record them in the task description.

---
*This file is automatically maintained by Agents as a collaboration contract.*
