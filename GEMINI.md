# Agent Collaboration and Context Optimization Guide (GEMINI.md)

This guide aims to standardize Agent skill activation behavior during development, optimize context consumption, and improve task execution efficiency.

## 1. Skills Activation Strategy

### Mandatory Entry
- **Required Every Time**: Before any user input/task begins, must check your skills list and first call `using-superpowers`.
- **Unified Dispatch**: Whether to trigger other skills afterwards is decided by `using-superpowers`.
- **No Exceptions**: Do not skip for reasons like "simple question" or "no skills needed".
- **Observability**: Must explicitly output an execution summary stating "triggered using-superpowers + whether other skills were dispatched".

### Precision Trigger Words
- **Analysis/Search**: Prefer calling the `search` sub-agent for read-only research, avoiding the main Agent getting bogged down in trivial searches.
- **Refactor/Optimize**: Use `refactor` or `optimize` to clarify intent.
- **Verify/Test**: Call `verify` or `test` skills immediately after making modifications.

### Intent Declaration
Agent should declare its "current working mode" before execution:
- `[PLANNING]`: Conducting multi-step task planning.
- `[EXECUTING]`: Executing specific code modifications.
- `[VERIFYING]`: Running tests to verify results.

## 2. Context Optimization

### Task Breakdown (Plan-and-Execute)
- Strictly prohibit executing more than 3 unrelated sub-tasks at once.
- Complex tasks must first generate `TODO.md` or call the `TodoWrite` tool.
- After each sub-task is completed, summarize core changes and "clean up" unnecessary intermediate context.

### Offloading
- **Large File Handling**: For files exceeding 500 lines, do not Read in full. First use `Grep` to locate, then perform localized reading.
- **Intermediate State**: Write complex analysis reports to `docs/notes/` or `tmp/`; the Agent only references their path and summary in subsequent conversations.

### Tool Selection Optimization
- **Search**: Use `Glob` when finding files, not `Grep`; use `Grep` when finding strings, not `SearchCodebase`.
- **Editing**: Prefer using `SearchReplace` for precise modifications, avoiding full rewrites.

## 3. Skills Control

### Core Principles
- **Load on Demand**: Only activate specific Skills when the task explicitly requires them.
- **Feedback Loop**: Each skill execution must provide a clear summary of execution results.
- **Avoid Redundancy**: If a task can be completed via standard CLI tools, do not create a complex custom Skill.

### Change Annotation
- **Mandatory Requirement**: After each modification to code, routes, configuration, or documentation, must add a brief comment at the modification point explaining the change purpose (Why), scope of impact (Scope), and verification method (Verify).
- **Annotation Format**:
  - Code files: Use appropriate inline/block comments near the change (JS/Vue use `//` or `/* */`; templates follow framework recommendations).
  - Documentation files: Add HTML comments `<!-- ... -->` adjacent to the adjusted paragraph describing this modification.
- **Security Constraints**: Comments must not contain sensitive information such as secrets, access tokens, or private links.
- **When Conflicting with User Preferences**: If the user explicitly prohibits adding comments, follow user instructions and record in the task description.

---
*This file is automatically maintained by the Agent as a collaboration contract.*
