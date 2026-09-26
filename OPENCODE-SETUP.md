# OpenCode and Codex setup

This guide runs the same local WhatsApp bridge and stdio MCP server in
OpenCode and Codex. It does not contain account data or credentials.

## Prepare the bridge

Install Go, Python 3.11+, and [uv](https://docs.astral.sh/uv/). Clone this
repository, then start the bridge in one terminal:

```sh
./start-bridge.sh
```

On first use, scan the QR code with WhatsApp's **Linked Devices** screen.
Keep the bridge running while using either client. The optional macOS
[launchd installer](README.md#run-automatically-on-macos) can start it at login.
The bridge's session, message databases, media, and API token stay under
`whatsapp-bridge/store/`; never commit that directory.

If the terminal QR code is hard to scan on macOS, stop the bridge and run
`python3 pair-whatsapp.py` from this checkout. The helper starts its own bridge,
opens each fresh QR in Preview, and leaves the bridge running after pairing.
It refuses to replace a bridge already listening on `WHATSAPP_BRIDGE_PORT`.
Private QR images and logs are written under
`~/Library/Logs/whatsapp-mcp/`. Do not publish them.

## Configure OpenCode

Add the server to the `mcp.servers` object in the OpenCode configuration for
the OS account that runs OpenCode, usually
`~/.config/opencode/opencode.jsonc`:

```jsonc
{
  "mcp": {
    "servers": {
      "whatsapp": {
        "type": "local",
        "command": ["/bin/sh", "/absolute/path/to/whatsapp-mcp/run-mcp-server.sh"]
      }
    }
  }
}
```

Merge the object into an existing file rather than replacing other settings.
Replace the path with this checkout's absolute path. Reload OpenCode and run
`opencode mcp list` to check the connection.

## Configure Codex

Add this to the `~/.codex/config.toml` used by the OS account running Codex:

```toml
[mcp_servers.whatsapp]
command = "/bin/sh"
args = ["/absolute/path/to/whatsapp-mcp/run-mcp-server.sh"]
startup_timeout_sec = 30
tool_timeout_sec = 120
```

Replace the path with this checkout's absolute path, restart Codex, then run
`codex mcp list` or inspect the connected tools in the Codex app. Codex's
[official MCP documentation](https://learn.chatgpt.com/docs/extend/mcp#configure-with-configtoml)
describes the `mcp_servers` table and stdio `command`/`args` settings.

## Why the launcher is used

`run-mcp-server.sh` installs locked Python dependencies on first use and
then replaces itself with the Python process. This lets the MCP server's
parent watchdog notice when its client disappears. It keeps a separate
virtual environment per OS user, which helps when the two clients run under
different accounts. A stale or missing environment is refreshed when
`pyproject.toml` or `uv.lock` changes.

If `uv` is not on the client's `PATH`, set `UV_BIN` to its absolute path in
that client's MCP environment. `WHATSAPP_MCP_VENV` can override the default
per-user virtual environment location. Both clients need read access to the
bridge store and its token. Prefer running the bridge and MCP clients as the
same OS user.

For a connection failure, check that the bridge is running, the path above
exists, and the MCP process can read `whatsapp-bridge/store/.bridge-token`.
Do not put the bridge token in the client config or a public issue.
