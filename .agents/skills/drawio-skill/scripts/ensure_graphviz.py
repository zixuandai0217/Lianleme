#!/usr/bin/env python3
"""Ensure Graphviz dot is available, installing Graphviz when possible."""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path


def has_dot() -> str | None:
    """Return the dot executable path when Graphviz is already available."""
    return shutil.which("dot")


def run(command: list[str], dry_run: bool = False) -> int:
    """Run an installation command, or print it in dry-run mode."""
    print("+ " + " ".join(command), file=sys.stderr)
    if dry_run:
        return 0
    try:
        return subprocess.run(command).returncode
    except FileNotFoundError:
        return 127


def run_capture(command: list[str], dry_run: bool = False) -> tuple[int, str]:
    """Run an installation command and return combined output for diagnosis."""
    print("+ " + " ".join(command), file=sys.stderr)
    if dry_run:
        return 0, ""
    try:
        proc = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except FileNotFoundError:
        return 127, ""
    if proc.stdout:
        print(proc.stdout, end="", file=sys.stderr)
    return proc.returncode, proc.stdout or ""


def command_exists(name: str) -> bool:
    """Check whether an executable exists on PATH."""
    return shutil.which(name) is not None


def mac_install_command() -> list[str] | None:
    """Return the preferred macOS Graphviz install command."""
    if command_exists("brew"):
        return ["brew", "install", "graphviz"]
    if command_exists("port"):
        return ["sudo", "port", "install", "graphviz"]
    return None


def linux_install_command() -> list[str] | None:
    """Return the preferred Linux Graphviz install command."""
    candidates = [
        ("apt-get", ["sudo", "apt-get", "update"], ["sudo", "apt-get", "install", "-y", "graphviz"]),
        ("apt", ["sudo", "apt", "update"], ["sudo", "apt", "install", "-y", "graphviz"]),
        ("dnf", None, ["sudo", "dnf", "install", "-y", "graphviz"]),
        ("yum", None, ["sudo", "yum", "install", "-y", "graphviz"]),
        ("pacman", None, ["sudo", "pacman", "-S", "--noconfirm", "graphviz"]),
        ("apk", None, ["sudo", "apk", "add", "graphviz"]),
    ]
    for binary, preflight, install in candidates:
        if command_exists(binary):
            if preflight:
                code = run(preflight)
                if code != 0:
                    print(f"warning: {' '.join(preflight)} exited {code}", file=sys.stderr)
            return install
    return None


def windows_install_command() -> list[str] | None:
    """Return the preferred Windows Graphviz install command."""
    if command_exists("winget"):
        return ["winget", "install", "--id", "Graphviz.Graphviz", "-e"]
    if command_exists("choco"):
        return ["choco", "install", "graphviz", "-y"]
    return None


def install_command() -> list[str] | None:
    """Choose an installation command for this platform."""
    system = platform.system().lower()
    if system == "darwin":
        return mac_install_command()
    if system == "linux":
        return linux_install_command()
    if system == "windows":
        return windows_install_command()
    return None


def backup_stale_homebrew_opt(output: str) -> bool:
    """Back up a stale Homebrew opt directory reported by brew link failures."""
    match = re.search(r"Directory not empty @ dir_s_rmdir - (/opt/homebrew/opt/[^\s]+)", output)
    if not match:
        return False
    path = Path(match.group(1))
    if not path.exists() or path.is_symlink() or not path.is_dir():
        return False
    backup = path.with_name(f"{path.name}.codex-backup")
    suffix = 0
    while backup.exists():
        suffix += 1
        backup = path.with_name(f"{path.name}.codex-backup-{suffix}")
    path.rename(backup)
    print(f"Moved stale Homebrew opt directory to {backup}", file=sys.stderr)
    return True


def append_common_graphviz_paths() -> None:
    """Add common install locations to PATH for the current process."""
    extra = [
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/opt/local/bin",
        r"C:\Program Files\Graphviz\bin",
        r"C:\Program Files (x86)\Graphviz\bin",
    ]
    existing = os.environ.get("PATH", "")
    parts = existing.split(os.pathsep) if existing else []
    for candidate in extra:
        if candidate not in parts and Path(candidate).exists():
            parts.append(candidate)
    os.environ["PATH"] = os.pathsep.join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure Graphviz dot is installed and on PATH.")
    parser.add_argument("--dry-run", action="store_true", help="Print the install command without running it.")
    args = parser.parse_args()

    append_common_graphviz_paths()
    dot = has_dot()
    if dot:
        print(dot)
        return 0

    command = install_command()
    if not command:
        print(
            "ERROR: Graphviz `dot` is missing and no supported package manager was found. "
            "Install Graphviz manually from https://graphviz.org/download/.",
            file=sys.stderr,
        )
        return 2

    code, output = run_capture(command, dry_run=args.dry_run)
    if args.dry_run:
        return code
    if code != 0 and command[:3] == ["brew", "install", "graphviz"] and backup_stale_homebrew_opt(output):
        print("Retrying Graphviz install after backing up stale Homebrew opt directory...", file=sys.stderr)
        code, output = run_capture(command)
    if code != 0:
        print(f"ERROR: Graphviz install command exited with status {code}", file=sys.stderr)
        return code

    append_common_graphviz_paths()
    dot = has_dot()
    if dot:
        print(dot)
        return 0

    print(
        "ERROR: Graphviz install command completed but `dot` is still not on PATH. "
        "Restart the shell or add the Graphviz bin directory to PATH.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
