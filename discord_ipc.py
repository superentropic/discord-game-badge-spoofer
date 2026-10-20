"""
discord_ipc.py - Native Discord Local IPC Client.

Connects to Discord's local IPC Unix domain socket or Windows named pipe
to broadcast verified Rich Presence activity.
"""

import json
import os
import platform
import socket
import struct
import sys
import time
import uuid
from typing import Optional, Dict, Any

OP_HANDSHAKE = 0
OP_FRAME = 1
OP_CLOSE = 2
OP_PING = 3
OP_PONG = 4


class DiscordIPCClient:
    """Interacts directly with the local Discord Desktop IPC server."""

    def __init__(self, client_id: str):
        self.client_id = str(client_id)
        self.sock: Optional[socket.socket] = None
        self.is_connected = False
        self.pipe_path: Optional[str] = None
        self.pid = os.getpid()

    def _get_pipe_paths(self):
        """Yield platform-specific potential Discord IPC socket/pipe paths."""
        system = platform.system()
        if system == "Windows":
            for i in range(10):
                yield rf"\\.\pipe\discord-ipc-{i}"
        else:
            base_dirs = [
                os.environ.get("XDG_RUNTIME_DIR"),
                f"/run/user/{os.getuid()}" if hasattr(os, "getuid") else None,
                os.environ.get("TMPDIR"),
                os.environ.get("TMP"),
                os.environ.get("TEMP"),
                "/tmp",
            ]
            for base in base_dirs:
                if base and os.path.isdir(base):
                    for i in range(10):
                        candidate = os.path.join(base, f"discord-ipc-{i}")
                        yield candidate

    def connect(self) -> bool:
        """Locate active Discord IPC endpoint and complete opcode 0 handshake."""
        system = platform.system()
        for path in self._get_pipe_paths():
            if not path:
                continue
            try:
                if system == "Windows":
                    # On Windows, named pipes can be opened like files
                    # or via socket/overlays. If file open is needed:
                    self.sock = open(path, "r+b", buffering=0)  # type: ignore
                else:
                    if not os.path.exists(path):
                        continue
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.settimeout(3.0)
                    s.connect(path)
                    self.sock = s

                self.pipe_path = path
                # Send Handshake
                handshake_payload = json.dumps({
                    "v": 1,
                    "client_id": self.client_id
                }).encode("utf-8")
                self._send(OP_HANDSHAKE, handshake_payload)

                opcode, resp = self._receive()
                if opcode == OP_FRAME and resp.get("evt") == "READY":
                    self.is_connected = True
                    return True
                elif opcode == OP_CLOSE:
                    self.close()
            except Exception:
                self.close()
                continue

        return False

    def _send(self, opcode: int, payload: bytes) -> None:
        """Pack 8-byte header and send payload."""
        if not self.sock:
            raise ConnectionError("Not connected to Discord IPC.")
        header = struct.pack("<II", opcode, len(payload))
        if hasattr(self.sock, "sendall"):
            self.sock.sendall(header + payload)
        else:
            self.sock.write(header + payload)  # Windows pipe file handle

    def _receive(self) -> tuple[int, Dict[str, Any]]:
        """Read 8-byte header and parse JSON payload."""
        if not self.sock:
            raise ConnectionError("Not connected to Discord IPC.")

        def read_bytes(n: int) -> bytes:
            buf = bytearray()
            while len(buf) < n:
                if hasattr(self.sock, "recv"):
                    chunk = self.sock.recv(n - len(buf))
                else:
                    chunk = self.sock.read(n - len(buf))
                if not chunk:
                    raise ConnectionResetError("Connection closed while reading.")
                buf.extend(chunk)
            return bytes(buf)

        header = read_bytes(8)
        opcode, length = struct.unpack("<II", header)
        payload = read_bytes(length).decode("utf-8")
        return opcode, json.loads(payload)

    def set_activity(
        self,
        details: str = "Playing game",
        state: str = "In Main Menu",
        start_time: Optional[int] = None,
        large_image: Optional[str] = None,
        large_text: Optional[str] = None,
        small_image: Optional[str] = None,
        small_text: Optional[str] = None,
    ) -> bool:
        """
        Send SET_ACTIVITY command.
        start_time: Epoch timestamp in seconds; required for Discord to display
                    the running stopwatch and accumulate Game Time badge hours.
        """
        if not self.is_connected:
            if not self.connect():
                return False

        if start_time is None:
            start_time = int(time.time())

        activity: Dict[str, Any] = {
            "details": details,
            "state": state,
            "timestamps": {"start": start_time},
            "instance": True,
        }

        assets: Dict[str, str] = {}
        if large_image:
            assets["large_image"] = large_image
        if large_text:
            assets["large_text"] = large_text
        if small_image:
            assets["small_image"] = small_image
        if small_text:
            assets["small_text"] = small_text

        if assets:
            activity["assets"] = assets

        frame = {
            "cmd": "SET_ACTIVITY",
            "args": {
                "pid": self.pid,
                "activity": activity,
            },
            "nonce": str(uuid.uuid4()),
        }

        try:
            payload = json.dumps(frame).encode("utf-8")
            self._send(OP_FRAME, payload)
            opcode, resp = self._receive()
            return resp.get("cmd") == "SET_ACTIVITY"
        except Exception as e:
            self.close()
            return False

    def clear_activity(self) -> bool:
        """Clear current activity from Discord."""
        if not self.is_connected:
            return True
        frame = {
            "cmd": "SET_ACTIVITY",
            "args": {
                "pid": self.pid,
                "activity": None,
            },
            "nonce": str(uuid.uuid4()),
        }
        try:
            payload = json.dumps(frame).encode("utf-8")
            self._send(OP_FRAME, payload)
            self._receive()
            return True
        except Exception:
            return False

    def close(self) -> None:
        """Cleanly close socket connection."""
        self.is_connected = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
