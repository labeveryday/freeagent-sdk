"""
Built-in tools for FreeAgent.
Useful defaults that work out of the box.
"""

from .system_info import system_info
from .calculator import calculator
from .shell import shell_exec

__all__ = ["system_info", "calculator", "shell_exec"]
