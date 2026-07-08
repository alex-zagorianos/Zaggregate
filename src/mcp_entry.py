"""Console entry point for the bundled MCP server — packaged as `Zaggregate-MCP.exe`.

Claude Code (or any MCP client) spawns this over stdio to drive the app's job-search
tools with **no separate Python and no repo clone** — the server code is already
inside the installed exe. See `agentchannel.ensure_agent_folder()` for the `.mcp.json`
that points a client here.

Why a dedicated CONSOLE exe (not a `--mcp` flag on the windowed `JobProgram.exe`):
MCP is a stdio protocol, and a `--windowed`/`--noconsole` PyInstaller build has its
`sys.stdin/stdout` set to null — the handshake would never complete. A console-subsystem
exe has real stdio; when an MCP client spawns it as a subprocess no console window shows.

All it does is run `mcp_server.main()` (bootstrap the data folder → pin the active
project → serve the 19 tools over stdio).
"""
import sys
from pathlib import Path

# Dev run: make src/ importable. Frozen: _MEIPASS is already on sys.path (harmless).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp_server import main

if __name__ == "__main__":
    main()
