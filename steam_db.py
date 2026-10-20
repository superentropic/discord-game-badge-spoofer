"""
steam_db.py - SteamDB & Discord Detectable Games Database Interface.

Handles resolving SteamDB URLs and AppIDs to Discord's official verified
application registry, extracting executable names, Discord Client IDs,
and metadata.
"""

import json
import os
import re
import urllib.request
import urllib.parse
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

DISCORD_DETECTABLE_URL = "https://discord.com/api/v9/applications/detectable"
CACHE_FILE = os.path.join(os.path.dirname(__file__), "data", "detectable_cache.json")

# Preloaded popular SteamDB games for instant zero-latency access
PRESET_GAMES = {
    "730": {
        "name": "Counter-Strike 2",
        "steam_appid": "730",
        "discord_id": "1158877933042143272",
        "exe_windows": "cs2.exe",
        "exe_linux": "cs2",
        "genres": ["Action", "FPS", "Tactical"],
    },
    "1091500": {
        "name": "Cyberpunk 2077",
        "steam_appid": "1091500",
        "discord_id": "787443973538971748",
        "exe_windows": "cyberpunk2077.exe",
        "exe_linux": "cyberpunk2077",
        "genres": ["Action", "RPG", "Open World"],
    },
    "1086940": {
        "name": "Baldur's Gate 3",
        "steam_appid": "1086940",
        "discord_id": "1137125502985961543",
        "exe_windows": "bg3.exe",
        "exe_linux": "bg3",
        "genres": ["RPG", "Strategy", "Turn-Based"],
    },
    "1245620": {
        "name": "ELDEN RING",
        "steam_appid": "1245620",
        "discord_id": "1402418436809953330",
        "exe_windows": "eldenring.exe",
        "exe_linux": "eldenring",
        "genres": ["Action", "RPG", "Souls-like"],
    },
    "440": {
        "name": "Team Fortress 2",
        "steam_appid": "440",
        "discord_id": "356888577310851072",
        "exe_windows": "hl2.exe",
        "exe_linux": "hl2_linux",
        "genres": ["Action", "FPS", "Multiplayer"],
    },
    "570": {
        "name": "Dota 2",
        "steam_appid": "570",
        "discord_id": "356875988589740042",
        "exe_windows": "dota2.exe",
        "exe_linux": "dota2",
        "genres": ["Action", "MOBA", "Strategy"],
    },
    "252490": {
        "name": "Rust",
        "steam_appid": "252490",
        "discord_id": "356877884486582272",
        "exe_windows": "RustClient.exe",
        "exe_linux": "RustClient",
        "genres": ["Survival", "Multiplayer", "Open World"],
    },
    "105600": {
        "name": "Terraria",
        "steam_appid": "105600",
        "discord_id": "356875567347392513",
        "exe_windows": "Terraria.exe",
        "exe_linux": "Terraria",
        "genres": ["Sandbox", "Adventure", "Survival"],
    },
    "271590": {
        "name": "Grand Theft Auto V",
        "steam_appid": "271590",
        "discord_id": "356869127271284736",
        "exe_windows": "GTA5.exe",
        "exe_linux": "GTA5",
        "genres": ["Action", "Open World", "Crime"],
    },
    "2379780": {
        "name": "Balatro",
        "steam_appid": "2379780",
        "discord_id": "1209930722379698206",
        "exe_windows": "Balatro.exe",
        "exe_linux": "Balatro",
        "genres": ["Roguelike", "Card Game", "Casual"],
    },
}

@dataclass
class GameEntry:
    name: str
    steam_appid: str
    steamdb_url: str
    discord_id: str
    exe_name: str
    all_executables: List[Dict[str, Any]]
    genres: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "steam_appid": self.steam_appid,
            "steamdb_url": self.steamdb_url,
            "discord_id": self.discord_id,
            "exe_name": self.exe_name,
            "genres": self.genres,
        }


class SteamDBDatabase:
    """Manages SteamDB and Discord Detectable Applications catalog."""

    def __init__(self, cache_file: str = CACHE_FILE):
        self.cache_file = cache_file
        self.apps_by_steam: Dict[str, Dict[str, Any]] = {}
        self.apps_by_name: Dict[str, Dict[str, Any]] = {}
        self.apps_by_discord: Dict[str, Dict[str, Any]] = {}
        self._load_database()

    def _load_database(self) -> None:
        """Load catalog from local cache or download if missing."""
        if not os.path.exists(self.cache_file):
            self.refresh_cache()

        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                apps = json.load(f)
            self._index_apps(apps)
        except Exception as e:
            print(f"[Warning] Failed loading local cache ({e}), using presets.")
            self._index_presets()

    def refresh_cache(self) -> bool:
        """Fetch latest detectable applications from Discord API."""
        print("[Catalog] Refreshing Discord detectable games catalog...")
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            req = urllib.request.Request(
                DISCORD_DETECTABLE_URL,
                headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            with open(self.cache_file, "wb") as f:
                f.write(data)
            apps = json.loads(data.decode("utf-8"))
            self._index_apps(apps)
            print(f"[Catalog] Successfully cached {len(apps)} detectable applications.")
            return True
        except Exception as e:
            print(f"[Catalog] Failed to download catalog: {e}")
            return False

    def _index_apps(self, apps: List[Dict[str, Any]]) -> None:
        """Build in-memory hash maps for fast lookup."""
        self.apps_by_steam.clear()
        self.apps_by_name.clear()
        self.apps_by_discord.clear()

        for app in apps:
            app_id = str(app.get("id"))
            self.apps_by_discord[app_id] = app

            name = app.get("name", "").strip()
            if name:
                self.apps_by_name[name.lower()] = app

            for sku in app.get("third_party_skus") or []:
                if sku.get("distributor") == "steam":
                    steam_id = str(sku.get("id")).strip()
                    self.apps_by_steam[steam_id] = app

    def _index_presets(self) -> None:
        """Fallback to presets if cache is unavailable."""
        for app_id, data in PRESET_GAMES.items():
            entry = {
                "id": data["discord_id"],
                "name": data["name"],
                "executables": [{"name": data["exe_windows"], "os": "win32"}],
                "third_party_skus": [{"distributor": "steam", "id": app_id}],
                "themes": data["genres"]
            }
            self.apps_by_steam[app_id] = entry
            self.apps_by_name[data["name"].lower()] = entry
            self.apps_by_discord[data["discord_id"]] = entry

    @staticmethod
    def extract_steam_appid(query: str) -> Optional[str]:
        """Extract numeric Steam AppID from raw ID, SteamDB URL, or Steam Store URL."""
        query = query.strip()
        # Direct numeric ID (e.g. 1091500)
        if query.isdigit():
            return query

        # SteamDB URL: https://steamdb.info/app/1091500/...
        m = re.search(r"steamdb\.info/app/(\d+)", query)
        if m:
            return m.group(1)

        # Steam store URL: https://store.steampowered.com/app/1091500/...
        m = re.search(r"store\.steampowered\.com/app/(\d+)", query)
        if m:
            return m.group(1)

        return None

    def lookup(self, query: str) -> Optional[GameEntry]:
        """
        Lookup a game by SteamDB AppID, SteamDB URL, Discord ID, or Name.
        """
        # 1. Try numeric Steam AppID
        steam_id = self.extract_steam_appid(query)
        if steam_id and steam_id in self.apps_by_steam:
            return self._build_game_entry(self.apps_by_steam[steam_id], steam_id)

        # Check in presets if not in cache
        if steam_id and steam_id in PRESET_GAMES:
            p = PRESET_GAMES[steam_id]
            return GameEntry(
                name=p["name"],
                steam_appid=steam_id,
                steamdb_url=f"https://steamdb.info/app/{steam_id}/",
                discord_id=p["discord_id"],
                exe_name=p["exe_windows"],
                all_executables=[{"name": p["exe_windows"], "os": "win32"}],
                genres=p["genres"],
            )

        # 2. Try Discord Application ID
        if query in self.apps_by_discord:
            app = self.apps_by_discord[query]
            steam_skus = [s["id"] for s in app.get("third_party_skus") or [] if s.get("distributor") == "steam"]
            s_id = str(steam_skus[0]) if steam_skus else "0"
            return self._build_game_entry(app, s_id)

        # 3. Try exact Name lookup
        q_lower = query.strip().lower()
        if q_lower in self.apps_by_name:
            app = self.apps_by_name[q_lower]
            steam_skus = [s["id"] for s in app.get("third_party_skus") or [] if s.get("distributor") == "steam"]
            s_id = str(steam_skus[0]) if steam_skus else "0"
            return self._build_game_entry(app, s_id)

        # 4. Partial name search
        for name, app in self.apps_by_name.items():
            if q_lower in name:
                steam_skus = [s["id"] for s in app.get("third_party_skus") or [] if s.get("distributor") == "steam"]
                s_id = str(steam_skus[0]) if steam_skus else "0"
                return self._build_game_entry(app, s_id)

        return None

    def search(self, query: str, limit: int = 10) -> List[GameEntry]:
        """Search for games matching a query string."""
        q_lower = query.strip().lower()
        results: List[GameEntry] = []
        for name, app in self.apps_by_name.items():
            if q_lower in name:
                steam_skus = [s["id"] for s in app.get("third_party_skus") or [] if s.get("distributor") == "steam"]
                s_id = str(steam_skus[0]) if steam_skus else "0"
                results.append(self._build_game_entry(app, s_id))
                if len(results) >= limit:
                    break
        return results

    def _build_game_entry(self, app: Dict[str, Any], steam_id: str) -> GameEntry:
        executables = app.get("executables") or []
        primary_exe = "game.exe"
        for exe in executables:
            if not exe.get("is_launcher", False) and exe.get("name"):
                name = exe.get("name")
                if name.startswith(">"):
                    name = name[1:]
                primary_exe = os.path.basename(name)
                break

        return GameEntry(
            name=app.get("name", "Unknown Game"),
            steam_appid=steam_id,
            steamdb_url=f"https://steamdb.info/app/{steam_id}/" if steam_id != "0" else "N/A",
            discord_id=str(app.get("id")),
            exe_name=primary_exe,
            all_executables=executables,
            genres=app.get("themes") or [],
        )

    def get_all_steam_games(self) -> List[GameEntry]:
        """Return all indexed Steam games as GameEntry objects for rotation."""
        games: List[GameEntry] = []
        for steam_id, app in self.apps_by_steam.items():
            if app.get("name") and app.get("id"):
                games.append(self._build_game_entry(app, steam_id))
        return games

