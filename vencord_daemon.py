"""
vencord_daemon.py - 24/7 Background Passive Game Spoofer for Vencord.

Features:
- Monitors Vencord / Vesktop / Discord process and local IPC socket.
- Runs passively 24/7 in the background.
- Plays as long as Vencord is open; pauses automatically when Vencord exits.
- Rotates through all 19,750+ verified SteamDB games in random shuffled order.
- Exact 5-minute duration per game.
- Persists state and statistics in data/vencord_daemon_state.json.
- Full daemon management: start, stop, restart, status, logs, install-systemd.
"""

import argparse
import ctypes
import glob
import json
import os
import platform
import random
import signal
import sys
import time
from typing import Optional, List, Dict, Any

from steam_db import SteamDBDatabase, GameEntry
from discord_ipc import DiscordIPCClient

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PID_FILE = os.path.join(DATA_DIR, "vencord_daemon.pid")
LOG_FILE = os.path.join(DATA_DIR, "vencord_daemon.log")
STATE_FILE = os.path.join(DATA_DIR, "vencord_daemon_state.json")
DEFAULT_ROTATION_SECONDS = 300  # 5 minutes


def log(msg: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] {msg}"
    print(entry, flush=True)


def is_vencord_running() -> bool:
    """
    Check if Vencord / Vesktop / Discord is running and its IPC socket is available.
    """
    # 1. Check for running processes
    vencord_proc = False
    if platform.system() == "Linux":
        pids = [pid for pid in os.listdir("/proc") if pid.isdigit()]
        for pid in pids:
            try:
                with open(f"/proc/{pid}/comm", "r") as f:
                    comm = f.read().strip().lower()
                    if any(x in comm for x in ["vesktop", "vencord", "discord"]):
                        vencord_proc = True
                        break
            except Exception:
                continue
    else:
        vencord_proc = True

    # 2. Check for active Discord IPC socket
    uid = os.getuid() if hasattr(os, "getuid") else 1000
    candidate_sockets = [
        f"/run/user/{uid}/discord-ipc-0",
        "/tmp/discord-ipc-0",
        *glob.glob("/run/user/*/discord-ipc-0"),
        *glob.glob("/tmp/discord-ipc-*"),
    ]
    socket_exists = any(os.path.exists(s) for s in candidate_sockets)

    return vencord_proc and socket_exists


def set_process_comm_name(name: str) -> None:
    """Set Linux /proc/self/comm to match the game executable."""
    if platform.system() == "Linux":
        try:
            libc = ctypes.CDLL(None)
            # PR_SET_NAME = 15 (max 15 chars + null byte)
            short_name = name[:15].encode("utf-8")
            libc.prctl(15, short_name, 0, 0, 0)
        except Exception:
            pass


def create_steam_appid_file(appid: str) -> None:
    """Generate steam_appid.txt matching Steam SDK."""
    try:
        with open(os.path.join(BASE_DIR, "steam_appid.txt"), "w") as f:
            f.write(f"{appid}\n")
    except Exception:
        pass


class VencordDaemon:
    def __init__(self, rotation_seconds: int = DEFAULT_ROTATION_SECONDS):
        self.rotation_seconds = rotation_seconds
        self.db = SteamDBDatabase()
        self.games_pool: List[GameEntry] = []
        self.pool_index = 0
        self.is_running = True
        self.current_client: Optional[DiscordIPCClient] = None
        self.current_game: Optional[GameEntry] = None
        self.game_start_time = 0
        self.total_games_played = 0
        self.total_seconds_played = 0
        self.history: List[Dict[str, Any]] = []

        self._load_state()
        self._init_pool()

    def _init_pool(self) -> None:
        """Fetch all 19,750+ SteamDB games and shuffle them randomly."""
        all_games = self.db.get_all_steam_games()
        if not all_games:
            raise RuntimeError("No detectable Steam games found in database catalog.")
        random.shuffle(all_games)
        self.games_pool = all_games
        self.pool_index = 0
        log(f"Initialized randomized pool of {len(self.games_pool)} verified SteamDB games.")

    def _load_state(self) -> None:
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.total_games_played = data.get("total_games_played", 0)
                self.total_seconds_played = data.get("total_seconds_played", 0)
                self.history = data.get("recent_history", [])
            except Exception:
                pass

    def _save_state(self, status_text: str = "RUNNING") -> None:
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            state = {
                "vencord_status": status_text,
                "current_game": self.current_game.to_dict() if self.current_game else None,
                "current_game_elapsed_seconds": int(time.time() - self.game_start_time) if self.game_start_time else 0,
                "rotation_interval_seconds": self.rotation_seconds,
                "total_games_played": self.total_games_played,
                "total_playtime_minutes": round(self.total_seconds_played / 60, 1),
                "pool_total_games": len(self.games_pool),
                "pool_current_index": self.pool_index,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "recent_history": self.history[-15:],
            }
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception:
            pass

    def _next_game(self) -> GameEntry:
        """Select next game from shuffled pool; reshuffle when exhausted."""
        if self.pool_index >= len(self.games_pool):
            log("Completed full rotation cycle across all games. Reshuffling pool...")
            random.shuffle(self.games_pool)
            self.pool_index = 0

        game = self.games_pool[self.pool_index]
        self.pool_index += 1
        return game

    def _apply_game(self, game: GameEntry) -> bool:
        """Connect to Vencord IPC and set Rich Presence activity for the game."""
        if self.current_client:
            self.current_client.clear_activity()
            self.current_client.close()

        set_process_comm_name(game.exe_name)
        create_steam_appid_file(game.steam_appid)

        client = DiscordIPCClient(game.discord_id)
        if not client.connect():
            return False

        now = int(time.time())
        success = client.set_activity(
            details=f"Playing {game.name}",
            state="In Game",
            start_time=now,
        )

        if success:
            self.current_client = client
            self.current_game = game
            self.game_start_time = now
            self.total_games_played += 1
            self.history.append({
                "name": game.name,
                "steam_appid": game.steam_appid,
                "steamdb_url": game.steamdb_url,
                "played_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "duration_seconds": self.rotation_seconds,
            })
            log(
                f"🎮 [Playing {self.total_games_played}] {game.name} | "
                f"SteamDB: {game.steamdb_url} | Discord ID: {game.discord_id}"
            )
            self._save_state("ACTIVE (PLAYING)")
            return True
        else:
            client.close()
            return False

    def run(self) -> None:
        """Main 24/7 background loop."""
        log("=== Vencord 24/7 Game Spoofer Daemon Started ===")
        log(f"Rotation Interval: {self.rotation_seconds // 60} minutes ({self.rotation_seconds}s)")

        # Register signal handlers for clean termination
        signal.signal(signal.SIGINT, self._handle_exit)
        signal.signal(signal.SIGTERM, self._handle_exit)

        vencord_was_active = False

        while self.is_running:
            vencord_active = is_vencord_running()

            if not vencord_active:
                if vencord_was_active:
                    log("⏸️  Vencord/Vesktop closed. Entering standby mode until Vencord restarts...")
                    if self.current_client:
                        self.current_client.clear_activity()
                        self.current_client.close()
                        self.current_client = None
                    self._save_state("STANDBY (VENCORD CLOSED)")
                    vencord_was_active = False

                # Sleep 5 seconds and poll
                time.sleep(5)
                continue

            # Vencord is active
            if not vencord_was_active:
                log("▶️  Vencord/Vesktop detected! Initializing game session...")
                vencord_was_active = True

            # If no game is active or timer expired, pick next random game
            now = time.time()
            need_new_game = (
                self.current_game is None
                or self.current_client is None
                or not self.current_client.is_connected
                or (now - self.game_start_time) >= self.rotation_seconds
            )

            if need_new_game:
                target_game = self._next_game()
                connected = self._apply_game(target_game)
                if not connected:
                    log(f"Failed to connect IPC for {target_game.name}. Retrying in 5 seconds...")
                    time.sleep(5)
                    continue

            # Maintain session
            time.sleep(1)
            self.total_seconds_played += 1
            if self.total_seconds_played % 30 == 0:
                self._save_state("ACTIVE (PLAYING)")

        self._cleanup()

    def _handle_exit(self, signum, frame):
        log(f"Received signal {signum}. Shutting down cleanly...")
        self.is_running = False

    def _cleanup(self):
        log("Cleaning up Discord IPC and state...")
        if self.current_client:
            self.current_client.clear_activity()
            self.current_client.close()
        self._save_state("STOPPED")
        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
            except Exception:
                pass
        log("=== Vencord Game Spoofer Daemon Stopped ===")


# =====================================================================
# Daemon Process Management (Start, Stop, Status, Install-Systemd)
# =====================================================================

def daemonize():
    """Double-fork to detach process completely from terminal."""
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as e:
        sys.stderr.write(f"Fork #1 failed: {e}\n")
        sys.exit(1)

    os.setsid()
    os.umask(0)

    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as e:
        sys.stderr.write(f"Fork #2 failed: {e}\n")
        sys.exit(1)

    # Redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()
    si = open(os.devnull, "r")
    so = open(LOG_FILE, "a+")
    se = open(LOG_FILE, "a+")
    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())

    # Write PID
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def cmd_start(rotation_seconds: int = DEFAULT_ROTATION_SECONDS):
    if os.path.exists(PID_FILE):
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
        if os.path.exists(f"/proc/{pid}"):
            print(f"[Error] Vencord daemon is already running (PID: {pid}).")
            return
        else:
            os.remove(PID_FILE)

    print(f"[Starting] Launching Vencord Game Spoofer in background (Interval: {rotation_seconds // 60}m)...")
    daemonize()
    daemon = VencordDaemon(rotation_seconds=rotation_seconds)
    daemon.run()


def cmd_stop():
    if not os.path.exists(PID_FILE):
        print("[Info] Vencord daemon is not running (no PID file).")
        return

    with open(PID_FILE, "r") as f:
        pid = int(f.read().strip())

    try:
        os.kill(pid, signal.SIGTERM)
        print(f"[Stopping] Sent SIGTERM to daemon (PID: {pid}).")
        # Wait up to 5 seconds
        for _ in range(10):
            if not os.path.exists(f"/proc/{pid}"):
                break
            time.sleep(0.5)
        print("[Stopped] Daemon terminated successfully.")
    except ProcessLookupError:
        print(f"[Info] Process {pid} not found. Removing stale PID file.")
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
    except Exception as e:
        print(f"[Error] Failed to stop daemon: {e}")


def cmd_status():
    is_running = False
    pid = None
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            is_running = os.path.exists(f"/proc/{pid}")
        except Exception:
            pass

    print("\n" + "=" * 65)
    print("  VENCORD 24/7 DUMMY GAME SPOOFER STATUS")
    print("=" * 65)
    if is_running:
        print(f"  Daemon Status     : \033[92m● RUNNING (PID: {pid})\033[0m")
    else:
        print(f"  Daemon Status     : \033[91m○ STOPPED\033[0m")

    vencord_active = is_vencord_running()
    v_status = "\033[92mONLINE (Detected)\033[0m" if vencord_active else "\033[93mSTANDBY (Vencord Closed)\033[0m"
    print(f"  Vencord Process   : {v_status}")

    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                s = json.load(f)
            cur = s.get("current_game") or {}
            elapsed = s.get("current_game_elapsed_seconds", 0)
            interval = s.get("rotation_interval_seconds", 300)
            remaining = max(0, interval - elapsed)

            print(f"  Current Game      : {cur.get('name', 'None')}")
            print(f"  SteamDB Link      : {cur.get('steamdb_url', 'N/A')}")
            print(f"  Discord App ID    : {cur.get('discord_id', 'N/A')}")
            print(f"  Current Playtime  : {elapsed // 60}m {elapsed % 60}s (Next switch in {remaining // 60}m {remaining % 60}s)")
            print(f"  Total Games Farmed: {s.get('total_games_played', 0)} unique titles")
            print(f"  Total Playtime    : {s.get('total_playtime_minutes', 0)} minutes")
            print(f"  Catalog Pool Size : {s.get('pool_total_games', 0)} verified SteamDB games")
        except Exception:
            pass

    print(f"  Log File          : {LOG_FILE}")
    print("=" * 65 + "\n")


def cmd_logs():
    if not os.path.exists(LOG_FILE):
        print("[Info] No log file found yet.")
        return
    print(f"--- Tailing last 25 lines of {LOG_FILE} ---")
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
        for line in lines[-25:]:
            print(line, end="")


def cmd_install_systemd():
    """Create and enable a systemd user service for automated 24/7 boot execution."""
    service_dir = os.path.expanduser("~/.config/systemd/user")
    os.makedirs(service_dir, exist_ok=True)
    service_path = os.path.join(service_dir, "vencord-game-spoofer.service")

    service_content = f"""[Unit]
Description=Vencord 24/7 SteamDB Game Spoofer (Discord Badges)
After=network.target

[Service]
Type=simple
WorkingDirectory={BASE_DIR}
ExecStart=/usr/bin/python3 {os.path.abspath(__file__)} run --interval 300
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
"""
    with open(service_path, "w", encoding="utf-8") as f:
        f.write(service_content)

    print(f"[Systemd] Created service unit at: {service_path}")
    os.system("systemctl --user daemon-reload")
    os.system("systemctl --user enable vencord-game-spoofer.service")
    print("[Systemd] Enabled vencord-game-spoofer.service to start automatically with user session.")
    print("To start it now via systemd, run:")
    print("  systemctl --user start vencord-game-spoofer.service")
    print("To check status:")
    print("  systemctl --user status vencord-game-spoofer.service")


def main():
    parser = argparse.ArgumentParser(description="Vencord 24/7 Passive Game Spoofer")
    parser.add_argument("command", choices=["start", "stop", "restart", "status", "logs", "run", "install-systemd"],
                        help="Daemon control command")
    parser.add_argument("--interval", type=int, default=DEFAULT_ROTATION_SECONDS,
                        help="Rotation interval in seconds (default: 300 = 5 minutes)")
    args = parser.parse_args()

    if args.command == "start":
        cmd_start(args.interval)
    elif args.command == "stop":
        cmd_stop()
    elif args.command == "restart":
        cmd_stop()
        time.sleep(1)
        cmd_start(args.interval)
    elif args.command == "status":
        cmd_status()
    elif args.command == "logs":
        cmd_logs()
    elif args.command == "install-systemd":
        cmd_install_systemd()
    elif args.command == "run":
        # Foreground mode
        daemon = VencordDaemon(rotation_seconds=args.interval)
        daemon.run()


if __name__ == "__main__":
    main()
