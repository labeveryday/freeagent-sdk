"""Shell command execution tool (sandboxed)."""

import subprocess
from ..tool import tool


@tool
def shell_exec(command: str) -> dict:
    """Run a shell command and return the output. Use for system tasks.

    command: The shell command to execute, e.g. "ls -la" or "df -h"
    """
    # Block obviously dangerous commands
    dangerous = ["rm -rf", "mkfs", "dd if=", "> /dev/", "chmod 777 /"]
    if any(d in command for d in dangerous):
        return {"error": f"Command blocked for safety: {command}"}

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "stdout": result.stdout[:2000],  # cap output
            "stderr": result.stderr[:500] if result.stderr else "",
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out (30s limit)"}
    except Exception as e:
        return {"error": str(e)}
