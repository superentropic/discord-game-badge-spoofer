"""
dummy_game.py - Realistic Dummy Game Simulator with GUI HUD & Discord Sync.

Emulates a real PC game process with:
- OS process name matching the game's executable.
- Top-level OS Window with exact game title.
- steam_appid.txt creation for local Steam SDK hooks.
- Direct Discord IPC synchronization for verified Rich Presence.
- Real-time session playtime tracker (Game Time badge).
- Game rotation automation (Game Variety badge).
"""

import ctypes
import os
import platform
import sys
import time
import threading
from typing import Optional, List

from steam_db import GameEntry, SteamDBDatabase, PRESET_GAMES
from discord_ipc import DiscordIPCClient


def set_process_comm_name(name: str) -> None:
    """On Linux, set /proc/self/comm to match the game executable."""
    if platform.system() == "Linux":
        try:
            libc = ctypes.CDLL(None)
            # PR_SET_NAME = 15, limited to 15 chars + null byte
            short_name = name[:15].encode("utf-8")
            libc.prctl(15, short_name, 0, 0, 0)
        except Exception:
            pass


def create_steam_appid_file(appid: str, target_dir: str = ".") -> str:
    """Generate steam_appid.txt file matching Steam SDK behavior."""
    filepath = os.path.join(target_dir, "steam_appid.txt")
    try:
        with open(filepath, "w") as f:
            f.write(f"{appid}\n")
    except Exception:
        pass
    return filepath


class DummyGameSession:
    """Manages the lifecycle, Discord IPC sync, and timing of an emulated game."""

    def __init__(self, game: GameEntry, auto_rotate_interval: Optional[int] = None):
        self.game = game
        self.auto_rotate_interval = auto_rotate_interval  # seconds
        self.start_time = int(time.time())
        self.session_seconds = 0
        self.ipc_client: Optional[DiscordIPCClient] = None
        self.is_running = True
        self.ipc_connected = False
        self.playlist: List[GameEntry] = [game]
        self.playlist_index = 0

        # Set OS process name
        set_process_comm_name(self.game.exe_name)
        create_steam_appid_file(self.game.steam_appid)

        # Initialize Discord IPC
        self._init_ipc()

    def _init_ipc(self) -> None:
        if self.ipc_client:
            self.ipc_client.clear_activity()
            self.ipc_client.close()

        self.ipc_client = DiscordIPCClient(self.game.discord_id)
        self.ipc_connected = self.ipc_client.connect()
        if self.ipc_connected:
            self.ipc_client.set_activity(
                details=f"Playing {self.game.name}",
                state="In Session",
                start_time=self.start_time,
            )

    def switch_game(self, new_game: GameEntry) -> None:
        """Switch emulated game in place."""
        self.game = new_game
        self.start_time = int(time.time())
        self.session_seconds = 0
        set_process_comm_name(self.game.exe_name)
        create_steam_appid_file(self.game.steam_appid)
        self._init_ipc()

    def tick(self) -> None:
        """Call once per second to maintain session state."""
        self.session_seconds = int(time.time()) - self.start_time
        # Reconnect IPC if disconnected
        if not self.ipc_connected and self.ipc_client:
            if self.ipc_client.connect():
                self.ipc_connected = True
                self.ipc_client.set_activity(
                    details=f"Playing {self.game.name}",
                    state="In Session",
                    start_time=self.start_time,
                )

    def stop(self) -> None:
        """Stop session and clear Discord activity."""
        self.is_running = False
        if self.ipc_client:
            self.ipc_client.clear_activity()
            self.ipc_client.close()
        # Clean up steam_appid.txt
        if os.path.exists("steam_appid.txt"):
            try:
                os.remove("steam_appid.txt")
            except Exception:
                pass


class DummyGameGUI:
    """Tkinter-based Native Graphical Interface simulating a running PC game."""

    def __init__(self, session: DummyGameSession, db: SteamDBDatabase):
        import tkinter as tk
        from tkinter import ttk

        self.session = session
        self.db = db
        self.root = tk.Tk()
        self.root.title(f"{session.game.name}")
        self.root.geometry("640x480")
        self.root.minsize(580, 420)
        self.root.configure(bg="#0b0e14")

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._update_loop()

    def _build_ui(self) -> None:
        import tkinter as tk
        from tkinter import ttk

        # Header Frame
        header = tk.Frame(self.root, bg="#151922", height=60)
        header.pack(fill="x", side="top")

        self.title_label = tk.Label(
            header,
            text=self.session.game.name.upper(),
            font=("Helvetica", 16, "bold"),
            fg="#00ffcc",
            bg="#151922",
        )
        self.title_label.pack(side="left", padx=20, pady=12)

        self.status_badge = tk.Label(
            header,
            text="DISCORD: CONNECTING...",
            font=("Courier", 10, "bold"),
            fg="#ffaa00",
            bg="#202634",
            padx=10,
            pady=4,
        )
        self.status_badge.pack(side="right", padx=20, pady=12)

        # Center HUD Canvas
        self.canvas = tk.Canvas(self.root, bg="#0b0e14", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=20, pady=15)

        # Playtime Banner Frame
        playtime_box = tk.Frame(self.root, bg="#121620", bd=1, relief="ridge")
        playtime_box.pack(fill="x", padx=20, pady=(0, 10))

        tk.Label(
            playtime_box,
            text="SESSION PLAYTIME (DISCORD BADGE PROGRESS):",
            font=("Helvetica", 9, "bold"),
            fg="#8892b0",
            bg="#121620",
        ).pack(anchor="w", padx=15, pady=(8, 2))

        self.timer_label = tk.Label(
            playtime_box,
            text="00:00:00",
            font=("Courier", 28, "bold"),
            fg="#ffffff",
            bg="#121620",
        )
        self.timer_label.pack(anchor="w", padx=15, pady=(0, 8))

        # Metadata Frame
        meta_box = tk.Frame(self.root, bg="#121620", bd=1, relief="ridge")
        meta_box.pack(fill="x", padx=20, pady=(0, 10))

        self.meta_label = tk.Label(
            meta_box,
            text=f"SteamDB AppID: {self.session.game.steam_appid}  |  Executable: {self.session.game.exe_name}  |  Discord AppID: {self.session.game.discord_id}",
            font=("Courier", 9),
            fg="#64ffda",
            bg="#121620",
            padx=10,
            pady=6,
        )
        self.meta_label.pack(fill="x")

        # Controls Frame
        controls = tk.Frame(self.root, bg="#0b0e14")
        controls.pack(fill="x", padx=20, pady=(0, 15), side="bottom")

        btn_style = {"bg": "#1f2937", "fg": "#f3f4f6", "font": ("Helvetica", 10, "bold"), "bd": 0, "padx": 15, "pady": 6}

        self.prev_btn = tk.Button(controls, text="◀ Previous Preset", command=self._prev_game, **btn_style)
        self.prev_btn.pack(side="left", padx=5)

        self.next_btn = tk.Button(controls, text="Next Preset ▶", command=self._next_game, **btn_style)
        self.next_btn.pack(side="left", padx=5)

        self.rotate_var = tk.BooleanVar(value=bool(self.session.auto_rotate_interval))
        self.rotate_check = tk.Checkbutton(
            controls,
            text="Auto-Rotate Variety (every 10m)",
            variable=self.rotate_var,
            command=self._toggle_rotation,
            bg="#0b0e14",
            fg="#9ca3af",
            selectcolor="#1f2937",
            activebackground="#0b0e14",
            activeforeground="#ffffff",
            font=("Helvetica", 10),
        )
        self.rotate_check.pack(side="left", padx=15)

        quit_btn = tk.Button(controls, text="Exit Game", command=self._on_close, bg="#dc2626", fg="#ffffff", font=("Helvetica", 10, "bold"), bd=0, padx=15, pady=6)
        quit_btn.pack(side="right", padx=5)

    def _draw_hud(self) -> None:
        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 10 or h < 10:
            return

        # Draw grid
        for x in range(0, w, 40):
            self.canvas.create_line(x, 0, x, h, fill="#121722", width=1)
        for y in range(0, h, 40):
            self.canvas.create_line(0, y, w, y, fill="#121722", width=1)

        # Crosshair / Game center
        cx, cy = w // 2, h // 2
        self.canvas.create_oval(cx - 50, cy - 50, cx + 50, cy + 50, outline="#00ffcc", width=2)
        self.canvas.create_line(cx - 70, cy, cx + 70, cy, fill="#00ffcc", width=1)
        self.canvas.create_line(cx, cy - 70, cx, cy + 70, fill="#00ffcc", width=1)

        # Simulated FPS & Engine text
        self.canvas.create_text(20, 20, anchor="nw", text="RENDERER: DIRECT3D 12 / VULKAN (EMULATED)", fill="#00ffcc", font=("Courier", 10))
        self.canvas.create_text(20, 40, anchor="nw", text=f"FPS: 144.0  |  FRAME: {int(time.time() * 60) % 99999}", fill="#22c55e", font=("Courier", 10))
        self.canvas.create_text(20, 60, anchor="nw", text=f"STEAM OVERLAY HOOK: ACTIVE (APPID {self.session.game.steam_appid})", fill="#38bdf8", font=("Courier", 10))

    def _toggle_rotation(self) -> None:
        if self.rotate_var.get():
            self.session.auto_rotate_interval = 600  # 10 minutes
        else:
            self.session.auto_rotate_interval = None

    def _next_game(self) -> None:
        self.session.playlist_index = (self.session.playlist_index + 1) % len(self.session.playlist)
        self._apply_game(self.session.playlist[self.session.playlist_index])

    def _prev_game(self) -> None:
        self.session.playlist_index = (self.session.playlist_index - 1) % len(self.session.playlist)
        self._apply_game(self.session.playlist[self.session.playlist_index])

    def _apply_game(self, game: GameEntry) -> None:
        self.session.switch_game(game)
        self.root.title(f"{game.name}")
        self.title_label.config(text=game.name.upper())
        self.meta_label.config(
            text=f"SteamDB AppID: {game.steam_appid}  |  Executable: {game.exe_name}  |  Discord AppID: {game.discord_id}"
        )

    def _update_loop(self) -> None:
        if not self.session.is_running:
            return

        self.session.tick()

        # Update stopwatch
        hrs = self.session.session_seconds // 3600
        mins = (self.session.session_seconds % 3600) // 60
        secs = self.session.session_seconds % 60
        self.timer_label.config(text=f"{hrs:02d}:{mins:02d}:{secs:02d}")

        # Update Discord status badge
        if self.session.ipc_connected:
            self.status_badge.config(
                text="DISCORD: CONNECTED (PLAYING)",
                fg="#22c55e",
                bg="#064e3b"
            )
        else:
            self.status_badge.config(
                text="DISCORD: DISCONNECTED",
                fg="#ef4444",
                bg="#450a0a"
            )

        # Check auto-rotate
        if self.session.auto_rotate_interval:
            if self.session.session_seconds >= self.session.auto_rotate_interval:
                self._next_game()

        self._draw_hud()
        self.root.after(1000, self._update_loop)

    def _on_close(self) -> None:
        self.session.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def run_headless_cli(session: DummyGameSession) -> None:
    """Run simulated game in headless terminal mode."""
    print("=" * 65)
    print(f"  DUMMY DETECTABLE GAME RUNNER - ACTIVE")
    print(f"  Game Title       : {session.game.name}")
    print(f"  SteamDB AppID    : {session.game.steam_appid}")
    print(f"  SteamDB Link     : {session.game.steamdb_url}")
    print(f"  Discord App ID   : {session.game.discord_id}")
    print(f"  Executable Name  : {session.game.exe_name}")
    print("=" * 65)
    print("Press Ctrl+C to terminate the session.\n")

    try:
        while session.is_running:
            session.tick()
            hrs = session.session_seconds // 3600
            mins = (session.session_seconds % 3600) // 60
            secs = session.session_seconds % 60
            status_text = "CONNECTED (Playing)" if session.ipc_connected else "RECONNECTING..."
            sys.stdout.write(
                f"\r[Session] {session.game.name} | Time: {hrs:02d}:{mins:02d}:{secs:02d} | Discord IPC: {status_text}   "
            )
            sys.stdout.flush()

            if session.auto_rotate_interval and session.session_seconds >= session.auto_rotate_interval:
                session.playlist_index = (session.playlist_index + 1) % len(session.playlist)
                next_g = session.playlist[session.playlist_index]
                print(f"\n[Rotation] Auto-rotating to next game: {next_g.name}")
                session.switch_game(next_g)

            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nShutting down session...")
    finally:
        session.stop()
        print("Discord activity cleared. Exit complete.")
