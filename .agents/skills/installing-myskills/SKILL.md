---
name: installing-myskills
description: Install, download, deploy, or update the complete zixuandai0217/MySkills collection in the current directory or a specified target directory by running its official remote installer. Use only when the user explicitly requests the whole MySkills collection; do not use for a single skill or for skills from another repository.
---

# Install MySkills

Install the complete `.agents/skills/` collection with the repository's official remote `install.sh`. Do not copy or reimplement its installation logic.

## Workflow

1. Resolve the target directory.
   - Use the current working directory unless the user specifies another directory.
   - Resolve the target to an exact absolute path before installation.
   - Preserve spaces and special characters by shell-quoting the path.
   - Refuse `/`, the user's home directory, unresolved variables, glob patterns, or any other overly broad target. Ask for a narrower explicit directory instead.

2. Select the backup behavior.
   - Keep the installer's default `BACKUP=1`. If the target already contains `.agents`, the installer moves it to `.agents.bak.<timestamp>` before installing.
   - Use `BACKUP=0` only when the user explicitly asks to overwrite without a backup. This permanently removes the target's existing `.agents` directory.

3. Run the official installer.

   For the current working directory:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/zixuandai0217/MySkills/main/install.sh | bash
   ```

   For a specified target directory, replace `/path/to/target` with the shell-quoted resolved path:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/zixuandai0217/MySkills/main/install.sh | bash -s -- "/path/to/target"
   ```

   If the user explicitly disables backup, set the variable on `bash`, not on `curl`:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/zixuandai0217/MySkills/main/install.sh | BACKUP=0 bash -s -- "/path/to/target"
   ```

4. Verify the result independently of the command's exit status.
   - Confirm `<target>/.agents/skills/` exists.
   - Enumerate its immediate subdirectories, sort their names, and count them.
   - Confirm each reported skill directory contains `SKILL.md`.
   - If an existing `.agents` directory was backed up, capture and report the exact backup path printed by the installer.
   - Report success only after these checks pass. Otherwise report the failed checks and relevant installer output.

5. Summarize the installation.
   - State the resolved target directory.
   - State the installed skill count and names.
   - State the backup path when one was created, or that no backup was created.

Do not offer individual-skill selection: this workflow always installs the complete MySkills collection.
