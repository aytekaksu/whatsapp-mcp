"""Synthetic checks for the local QR parser and pairing process boundary."""

import importlib.util
import os
import socket
import stat
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]


def load_script(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


renderer = load_script("qr_renderer_test", "render-bridge-qr.py")
pairing = load_script("qr_pairing_test", "pair-whatsapp.py")


class QRPairingTests(unittest.TestCase):
    def test_parse_and_render_synthetic_terminal_qr(self):
        art = ["█" + " " * 20 for _ in range(10)] + ["▀" * 21]
        output = "\n".join([renderer.ANCHOR, *art, renderer.END])
        blocks = renderer.find_blocks(output)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(len(blocks[0]), 10)
        bitmap = renderer.to_bitmap(blocks[0])
        self.assertEqual((len(bitmap), len(bitmap[0])), (20, 21))

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "qr.png"
            renderer.write_png(bitmap, 2, path)
            data = path.read_bytes()
            self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(struct.unpack(">II", data[16:24]), (58, 56))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_existing_listener_is_detected(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            self.assertTrue(pairing.port_in_use(listener.getsockname()[1]))

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "requires O_NOFOLLOW")
    def test_renderer_does_not_follow_output_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target"
            target.write_text("unchanged")
            link = Path(directory) / "qr.png"
            link.symlink_to(target)
            with self.assertRaises(OSError):
                renderer.write_png([[True]], 1, link)
            self.assertEqual(target.read_text(), "unchanged")

    def test_existing_bridge_is_not_replaced(self):
        with (
            patch.object(sys, "platform", "darwin"),
            patch.object(sys, "argv", ["pair-whatsapp.py"]),
            patch.object(pairing, "port_in_use", return_value=True),
            patch.object(pairing, "start_bridge") as start,
        ):
            self.assertEqual(pairing.main(), 2)
            start.assert_not_called()

    def test_stop_only_the_supplied_process(self):
        process = Mock()
        process.poll.return_value = None
        pairing.stop_bridge(process)
        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=5)

    def test_success_leaves_own_bridge_running(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "whatsapp-bridge" / "whatsapp-bridge"
            binary.parent.mkdir()
            binary.write_text("#!/bin/sh\n")
            binary.chmod(0o700)
            logs = root / "logs"
            bridge_log = logs / "bridge.out.log"

            def start_with_success():
                bridge_log.write_text(pairing.SUCCESS_MARKERS[0])
                return Mock()

            with (
                patch.multiple(
                    pairing,
                    REPO_DIR=root,
                    LOG_DIR=logs,
                    QR_DIR=logs / "qr",
                    BRIDGE_LOG=bridge_log,
                ),
                patch.object(sys, "platform", "darwin"),
                patch.object(sys, "argv", ["pair-whatsapp.py", "--timeout", "1"]),
                patch.object(pairing.os, "umask"),
                patch.object(pairing, "port_in_use", return_value=False),
                patch.object(pairing, "start_bridge", side_effect=start_with_success),
                patch.object(pairing, "stop_bridge") as stop,
            ):
                self.assertEqual(pairing.main(), 0)
                stop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
