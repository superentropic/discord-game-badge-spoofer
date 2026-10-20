#!/usr/bin/env python3
"""
launcher.py - Main entry point for Discord Dummy Game Spoofer.

Usage Examples:
  # 1. Launch Cyberpunk 2077 using SteamDB URL
  python3 launcher.py --app https://steamdb.info/app/1091500/

  # 2. Launch Counter-Strike 2 using Steam AppID
  python3 launcher.py --app 730

  # 3. Search for any game in SteamDB / Discord catalog
  python3 launcher.py --search "Elden Ring"

  # 4. Auto-rotate through top games every 15 minutes (for Game Variety badge)
  python3 launcher.py --rotate 15

  # 5. Run in headless terminal mode (no GUI window)
  python3 launcher.py --app 730 --headless
"""

import argparse
import os
import sys

from steam_db import SteamDBDatabase, PRESET_GAMES, GameEntry
from dummy_game import DummyGameSession, DummyGameGUI, run_headless_cli


def build_playlist(db: SteamDBDatabase, selected_game: GameEntry) -> list[GameEntry]:
    """Build playlist starting with selected game, followed by top preset games."""
    playlist = [selected_game]
    for appid, p in PRESET_GAMES.items():
        if appid != selected_game.steam_appid:
            entry = db.lookup(appid)
            if entry:
                playlist.append(entry)
    return playlist


def main():
    parser = argparse.ArgumentParser(
        description="Discord Dummy Game Spoofer - Detectable Game Simulator for Discord Badges"
    )
    parser.add_argument(
        "--app",
        type=str,
        default="1091500",
        help="SteamDB URL (e.g. https://steamdb.info/app/1091500/) or Steam AppID (e.g. 1091500 or 730)",
    )
    parser.add_argument(
        "--search",
        type=str,
        help="Search for game titles in the SteamDB/Discord detectable games catalog",
    )
    parser.add_argument(
        "--rotate",
        type=int,
        nargs="?",
        const=15,
        default=None,
        metavar="MINUTES",
        help="Enable auto-rotation across detectable games every N minutes (default: 15) to test Game Variety badge",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run in headless CLI mode without creating a graphical window",
    )
    parser.add_argument(
        "--list-presets",
        action="store_true",
        help="List popular pre-configured SteamDB games",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Re-download latest detectable games catalog from Discord API",
    )

    args = parser.parse_args()

    db = SteamDBDatabase()

    if args.refresh_cache:
        db.refresh_cache()
        return

    if args.list_presets:
        print("\n" + "=" * 65)
        print("  POPULAR STEAMDB PRESETS READY FOR DISCORD BADGE TESTING")
        print("=" * 65)
        for appid, p in PRESET_GAMES.items():
            print(f" • [{appid:>7}] {p['name']:<25} | Exe: {p['exe_windows']:<18} | Discord ID: {p['discord_id']}")
        print("=" * 65 + "\n")
        return

    if args.search:
        results = db.search(args.search, limit=12)
        print(f"\nSearch results for '{args.search}':")
        if not results:
            print("  No games found. Try refreshing cache with --refresh-cache.")
        for r in results:
            print(f" • [{r.steam_appid:>7}] {r.name:<30} | SteamDB: {r.steamdb_url}")
        print()
        return

    # Lookup target game
    game = db.lookup(args.app)
    if not game:
        print(f"[Error] Could not find a detectable Discord game matching '{args.app}'.")
        print("Tip: Use --search <name> or pick from --list-presets.")
        sys.exit(1)

    rotate_interval = args.rotate * 60 if args.rotate else None
    session = DummyGameSession(game, auto_rotate_interval=rotate_interval)
    session.playlist = build_playlist(db, game)

    # Detect if display is available for GUI
    has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") or sys.platform == "win32")

    if args.headless or not has_display:
        if not has_display and not args.headless:
            print("[Info] No graphical display detected. Falling back to headless mode.")
        run_headless_cli(session)
    else:
        try:
            gui = DummyGameGUI(session, db)
            gui.run()
        except Exception as e:
            print(f"[Warning] GUI initialization failed ({e}), falling back to headless mode.")
            run_headless_cli(session)


if __name__ == "__main__":
    main()
