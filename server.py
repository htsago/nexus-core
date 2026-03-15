from __future__ import annotations

import importlib
import os
import pkgutil
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from fastmcp import FastMCP

from src.db import init_db

init_db()

mcp = FastMCP(
    name="NEXUS Core",
    instructions=(
        "Autonomous, deterministic RAG server for verified documentation. "
        "Every answer is grounded in indexed sources. "
        "No heuristics – no hallucinations."
    ),
    on_duplicate="error",
    mask_error_details=True,
)

import src.tools as _tools_pkg

for _, _name, _ in pkgutil.iter_modules(_tools_pkg.__path__):
    _mod = importlib.import_module(f"src.tools.{_name}")
    if hasattr(_mod, "register"):
        _mod.register(mcp)



if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=8765,
        stateless_http=True,
    )
