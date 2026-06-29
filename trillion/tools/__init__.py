"""The hands — tools the brain can choose to call.

Adding a capability means writing one self-contained tool and registering it,
never editing the core loop. That single rule is what lets Trillion grow without
becoming tangled.
"""

from trillion.tools.registry import Tool, ToolRegistry, ToolResult

__all__ = ["Tool", "ToolRegistry", "ToolResult"]
