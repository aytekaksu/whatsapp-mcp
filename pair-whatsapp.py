#!/usr/bin/env python3
"""Open fresh macOS WhatsApp pairing QR codes from the local bridge.

Run only when no bridge is listening. The helper stops only bridge processes it
started itself, and leaves the successful one running.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent
LOG_DIR = Path.home() / "Library" / "Logs" / "whatsapp-mcp"
BRIDGE_LOG = LOG_DIR / "bridge.out.log"
QR_DIR = LOG_DIR / "qr"

spec = importlib.util.spec_from_file_location("renderer", REPO_DIR / "render-bridge-qr.py")
renderer = importlib.util.module_from_spec(spec)
sys.modules["renderer"] = renderer
spec.loader.exec_module(renderer)

SUCCESS_MARKERS = (
    "Successfully connected and authenticated!",
    "\u2713 Successfully connected to WhatsApp servers",
)
FATAL_MARKERS = ("Failed to get QR channel", "Client outdated")


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def start_bridge() -> subprocess.Popen:
    env = dict(os.environ)
    env.setdefault("WHATSAPP_DEVICE_NAME", "WhatsApp MCP")
    with BRIDGE_LOG.open("a", encoding="utf-8", buffering=1) as log:
        log.write(f"\n=== bridge start {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        return subprocess.Popen(
            [str(REPO_DIR / "start-bridge.sh")],
            cwd=REPO_DIR,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=env,
            start_new_session=True,
        )


def stop_bridge(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=900, help="total pairing time in seconds")
    parser.add_argument("--cycle", type=int, default=45, help="seconds before asking for a fresh QR")
    args = parser.parse_args()

    if sys.platform != "darwin":
        parser.error("pair-whatsapp.py requires macOS Preview")
    if args.timeout <= 0 or args.cycle <= 0:
        parser.error("--timeout and --cycle must be positive")
    try:
        port = int(os.environ.get("WHATSAPP_BRIDGE_PORT", "8080"))
    except ValueError:
        parser.error("WHATSAPP_BRIDGE_PORT must be a number")
    if not 1 <= port <= 65535:
        parser.error("WHATSAPP_BRIDGE_PORT must be between 1 and 65535")
    if port_in_use(port):
        print(f"Bridge already listens on port {port}; stop it yourself before pairing.", file=sys.stderr)
        return 2

    # A first build may take longer than one QR cycle. Finish it before the
    # pairing deadline and before starting a process we might need to stop.
    binary = REPO_DIR / "whatsapp-bridge" / "whatsapp-bridge"
    if not os.access(binary, os.X_OK):
        subprocess.run(["go", "build", "-o", str(binary), "."], cwd=binary.parent, check=True)

    os.umask(0o077)
    LOG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    QR_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    LOG_DIR.chmod(0o700)
    QR_DIR.chmod(0o700)
    BRIDGE_LOG.touch()
    BRIDGE_LOG.chmod(0o600)

    deadline = time.monotonic() + args.timeout
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        offset = BRIDGE_LOG.stat().st_size
        proc = start_bridge()
        paired = False
        shown = 0
        try:
            cycle_end = min(deadline, time.monotonic() + args.cycle)
            while time.monotonic() < cycle_end:
                with BRIDGE_LOG.open(encoding="utf-8", errors="replace") as log:
                    log.seek(offset)
                    output = log.read()
                if any(marker in output for marker in SUCCESS_MARKERS):
                    paired = True
                    print("PAIRED: WhatsApp linked. Bridge left running.", flush=True)
                    return 0
                if any(marker in output for marker in FATAL_MARKERS):
                    print("Bridge cannot pair; check the private bridge log.", file=sys.stderr)
                    return 1
                blocks = renderer.find_blocks(output)
                if len(blocks) > shown:
                    shown = len(blocks)
                    image = QR_DIR / f"whatsapp-qr-{attempt:02d}-{shown:02d}.png"
                    renderer.write_png(renderer.to_bitmap(blocks[-1]), 14, image)
                    subprocess.run(["open", "-a", "Preview", str(image)], check=False)
                    print(f"QR #{attempt}.{shown} ready: {image}", flush=True)
                if proc.poll() is not None or "QR code timed out" in output:
                    break
                time.sleep(1)
        finally:
            if not paired:
                stop_bridge(proc)
        if time.monotonic() < deadline:
            print("Requesting a fresh QR code...", flush=True)

    print("TIMEOUT: pairing did not finish.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
