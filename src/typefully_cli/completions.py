"""Shell completion install and show commands."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import click

from typefully_cli.console import Console, write_success
from typefully_cli.exceptions import TypefullyError


SHELL_CHOICES = ("bash", "zsh", "fish")

ALIAS_LINE = 'alias tf=typefully'

SCRIPT_PATHS = {
    "bash": Path.home() / ".typefully-complete.bash",
    "zsh": Path.home() / ".typefully-complete.zsh",
    "fish": Path.home() / ".config" / "fish" / "completions" / "typefully.fish",
}

RC_PATHS = {
    "bash": Path.home() / ".bashrc",
    "zsh": Path.home() / ".zshrc",
}


def _detect_shell() -> str:
    shell_env = os.environ.get("SHELL", "")
    for name in SHELL_CHOICES:
        if name in shell_env:
            return name
    raise TypefullyError(
        f"Could not detect shell from $SHELL={shell_env!r}",
        code="invalid_input",
        hint="Pass --shell bash|zsh|fish explicitly",
    )


def _generate_script(shell: str) -> str:
    env_var = f"_{cli_prog_name().upper()}_COMPLETE"
    env = {**os.environ, env_var: f"{shell}_source"}
    result = subprocess.run(
        [sys.executable, "-m", "typefully_cli"],
        env=env,
        capture_output=True,
        text=True,
    )
    # Click writes the completion script to stdout and exits
    if result.stdout.strip():
        return result.stdout
    # Fallback: try running the console_scripts entry point directly
    result = subprocess.run(
        ["typefully"],
        env=env,
        capture_output=True,
        text=True,
    )
    return result.stdout


def cli_prog_name() -> str:
    return "typefully"


def _source_line(shell: str) -> str:
    script_path = SCRIPT_PATHS[shell]
    return f"source {script_path}"


def _rc_already_sourced(rc_path: Path, source_line: str) -> bool:
    if not rc_path.exists():
        return False
    content = rc_path.read_text()
    return source_line in content


@click.group()
def completions():
    """Manage shell completions."""


@completions.command("install")
@click.option(
    "--shell", "shell_name", default=None,
    type=click.Choice(SHELL_CHOICES),
    help="Shell to install for (auto-detected from $SHELL if omitted)",
)
def completions_install(shell_name: str | None):
    """Auto-detect shell, write completion script, and update rc file."""
    console = Console(quiet=False)
    try:
        shell = shell_name or _detect_shell()
        script = _generate_script(shell)

        if not script.strip():
            raise TypefullyError(
                "Failed to generate completion script",
                code="internal_error",
                hint="Try running: _TYPEFULLY_COMPLETE={}_source typefully".format(shell),
            )

        script_path = SCRIPT_PATHS[shell]
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(script)

        rc_updated = False
        alias_added = False
        rc_path_str = ""

        if shell in RC_PATHS:
            rc_path = RC_PATHS[shell]
            rc_path_str = str(rc_path)
            source = _source_line(shell)
            additions = []
            if not _rc_already_sourced(rc_path, source):
                additions.append(source)
                rc_updated = True
            if not _rc_already_sourced(rc_path, ALIAS_LINE):
                additions.append(ALIAS_LINE)
                alias_added = True
            if additions:
                with open(rc_path, "a") as f:
                    f.write("\n" + "\n".join(additions) + "\n")
        elif shell == "fish":
            # Fish alias: write a function file
            fish_fn = Path.home() / ".config" / "fish" / "functions" / "tf.fish"
            if not fish_fn.exists():
                fish_fn.parent.mkdir(parents=True, exist_ok=True)
                fish_fn.write_text("function tf\n    typefully $argv\nend\n")
                alias_added = True

        result = {
            "shell": shell,
            "script_path": str(script_path),
            "alias_added": alias_added,
        }
        if rc_path_str:
            result["rc_path"] = rc_path_str
            result["rc_updated"] = rc_updated

        write_success(result)

        if shell == "fish":
            console.status(f"Completions installed to {script_path}")
        else:
            rc = RC_PATHS[shell]
            if rc_updated or alias_added:
                console.status(f"Completions + alias 'tf' installed. Restart your shell or run: source {rc}")
            else:
                console.status(
                    f"Completions + alias already in {rc}."
                )

    except TypefullyError as e:
        console.error_json(e.to_dict())
        sys.exit(1)


@completions.command("show")
@click.option(
    "--shell", "shell_name", default=None,
    type=click.Choice(SHELL_CHOICES),
    help="Shell to generate for (auto-detected from $SHELL if omitted)",
)
def completions_show(shell_name: str | None):
    """Print the raw completion script to stdout."""
    console = Console(quiet=False)
    try:
        shell = shell_name or _detect_shell()
        script = _generate_script(shell)
        if not script.strip():
            raise TypefullyError(
                "Failed to generate completion script",
                code="internal_error",
            )
        # Raw script, no JSON wrapper
        sys.stdout.write(script)
        sys.stdout.flush()
    except TypefullyError as e:
        console.error_json(e.to_dict())
        sys.exit(1)
