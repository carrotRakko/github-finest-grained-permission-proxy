"""
Command modules for fgp proxy.

Each command module provides:
- ACTIONS: List of action strings this command uses
- CLI_COMMANDS: Mapping of CLI args pattern to action
- execute(): Function to execute the command
"""

from . import discussion
from . import issue
from . import sub_issue

# Registry of all command modules
COMMAND_MODULES = {
    "discussion": discussion,
    "issue": issue,
    "sub-issue": sub_issue,
}


def get_cli_action(cmd: str, subcmd: str | None, args: list[str]) -> tuple[str | None, str | None]:
    """
    Get action for CLI command.

    Returns:
        (action, error_message)
        - If action is found: (action, None)
        - If explicitly forbidden: (None, error_message)
        - If unknown: (None, None)
    """
    if cmd in COMMAND_MODULES:
        module = COMMAND_MODULES[cmd]
        return module.get_action(subcmd, args)
    return None, None


def execute_command(
    cmd: str,
    args: list[str],
    owner: str,
    repo: str,
    pat: str
) -> dict:
    """
    Execute a command.

    Returns:
        {"exit_code": int, "stdout": str, "stderr": str}
    """
    if cmd not in COMMAND_MODULES:
        raise ValueError(f"Unknown command: {cmd}")

    module = COMMAND_MODULES[cmd]
    return module.execute(args, owner, repo, pat)


def get_all_command_actions() -> list[str]:
    """Get all actions from all command modules."""
    actions = []
    for module in COMMAND_MODULES.values():
        actions.extend(module.ACTIONS)
    return actions
