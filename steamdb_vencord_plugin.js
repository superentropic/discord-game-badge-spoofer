// === VENCORD 24/7 STEAMDB GAME BADGE SPOOFER AUTO-PLUGIN ===
(function initSteamDbBadgeSpoofer() {
    const PLAY_DURATION_MS = 20 * 60 * 1000; // 20 minutes active play
    const REST_DURATION_MS = 2 * 60 * 1000;  // 2 minutes offline break between games

    async function start() {
        while (!window.Vencord?.Webpack?.findStore || !window.Vencord?.Webpack?.Common?.FluxDispatcher) {
            await new Promise(r => setTimeout(r, 1000));
        }

        const runStore = Vencord.Webpack.findStore("RunningGameStore") || Vencord.Webpack.findByProps("getRunningGames");
        const dispatcher = Vencord.Webpack.Common.FluxDispatcher || Vencord.Webpack.findByProps("dispatch", "subscribe");

        if (!runStore || !dispatcher) {
            setTimeout(start, 2000);
            return;
        }

        if (!window.DiscordNative) window.DiscordNative = {};
        if (!window.DiscordNative.nativeModules) {
            window.DiscordNative.nativeModules = {
                requireModule: () => ({
                    GetWindowFullscreenTypeByPid: () => 0,
                    init: () => {},
                    setOverlayCallback: () => {}
                }),
                ensureModule: () => Promise.resolve()
            };
        }

        const utilsMod = Vencord.Webpack?.findByProps?.("getDiscordUtils");
        if (utilsMod) {
            utilsMod.getDiscordUtils = () => ({ GetWindowFullscreenTypeByPid: () => 0 });
        }

        let rawCatalog = [];
        try {
            const res = await fetch("/api/v9/applications/detectable");
            rawCatalog = await res.json();
        } catch (err) {
            setTimeout(start, 10000);
            return;
        }

        const STEAM_GAMES = [];
        for (const app of rawCatalog) {
            const steamSku = app.third_party_skus?.find(s => s.distributor === "steam");
            if (steamSku?.id && app.name && app.id) {
                let exeName = "game.exe";
                if (app.executables?.length > 0) {
                    const best = app.executables.find(e => !e.is_launcher && e.name) || app.executables[0];
                    if (best?.name) {
                        let n = best.name.startsWith(">") ? best.name.slice(1) : best.name;
                        exeName = n.split("/").pop().split("\\").pop();
                    }
                }
                STEAM_GAMES.push({
                    name: app.name,
                    appId: String(app.id),
                    steamId: String(steamSku.id),
                    steamdbUrl: "https://steamdb.info/app/" + steamSku.id + "/",
                    exe: exeName
                });
            }
        }

        console.log(
            "%c[SteamDB Auto-Plugin] Successfully initialized " + STEAM_GAMES.length.toLocaleString() + " REAL SteamDB games!",
            "color: #22c55e; font-weight: bold; font-size: 14px;"
        );

        const originalGetRunning = runStore.getRunningGames;
        const originalGetGameForPID = runStore.getGameForPID;
        const pid = 58291;
        let currentGame = null;
        let isResting = false;
        let activeTimeout = null;
        const playedHistory = new Set();

        runStore.getRunningGames = function() {
            const real = originalGetRunning ? originalGetRunning.apply(this, arguments) : [];
            return currentGame ? [...real.filter(g => g?.pid !== pid), currentGame] : real;
        };
        runStore.getGameForPID = function(p) {
            if (p === pid && currentGame) return currentGame;
            return originalGetGameForPID ? originalGetGameForPID.apply(this, arguments) : null;
        };

        function pickRandomSteamGame() {
            if (playedHistory.size >= STEAM_GAMES.length) playedHistory.clear();
            let candidate;
            for (let tries = 0; tries < 50; tries++) {
                candidate = STEAM_GAMES[Math.floor(Math.random() * STEAM_GAMES.length)];
                if (!playedHistory.has(candidate.steamId)) break;
            }
            playedHistory.add(candidate.steamId);
            return candidate;
        }

        function clearGame() {
            if (currentGame) {
                dispatcher.dispatch({ type: "RUNNING_GAMES_CHANGE", added: [], removed: [currentGame], games: [] });
                dispatcher.dispatch({ type: "LOCAL_ACTIVITY_UPDATE", socketId: "BadgeSpoofer", activity: null });
                currentGame = null;
            }
        }

        function setGame(item) {
            clearGame();
            isResting = false;
            const now = Date.now();
            currentGame = {
                id: item.appId,
                name: item.name,
                pid: pid,
                pidPath: [pid],
                processName: item.name,
                start: now,
                exeName: item.exe,
                exePath: "/usr/games/" + item.exe,
                cmdLine: "/usr/games/" + item.exe,
                windowHandle: 1,
                fullscreenType: 0,
                overlay: false,
                sandboxed: false,
                hidden: false,
                isLauncher: false
            };

            dispatcher.dispatch({
                type: "RUNNING_GAMES_CHANGE",
                added: [currentGame],
                removed: [],
                games: runStore.getRunningGames()
            });

            dispatcher.dispatch({
                type: "LOCAL_ACTIVITY_UPDATE",
                socketId: "BadgeSpoofer",
                activity: {
                    application_id: item.appId,
                    name: item.name,
                    type: 0,
                    details: "In Game",
                    state: "Playing",
                    timestamps: { start: now },
                    flags: 1
                }
            });

            console.log(
                "%c[SteamDB Auto-Plugin] 🎮 Playing: " + item.name + " (" + item.steamdbUrl + ")\n" +
                "  • Duration: " + (PLAY_DURATION_MS / 60000) + " mins | History: " + playedHistory.size + " unique titles",
                "color: #38bdf8; font-weight: bold;"
            );

            activeTimeout = setTimeout(enterRestBreak, PLAY_DURATION_MS);
        }

        function enterRestBreak() {
            isResting = true;
            clearGame();
            console.log(
                "%c[SteamDB Auto-Plugin] ☕ Resting for " + (REST_DURATION_MS / 60000) + " minutes before launching next Steam game...",
                "color: #a78bfa; font-weight: bold;"
            );
            activeTimeout = setTimeout(() => {
                setGame(pickRandomSteamGame());
            }, REST_DURATION_MS);
        }

        setGame(pickRandomSteamGame());

        window.__badgeSpoofer = {
            next: () => {
                clearTimeout(activeTimeout);
                setGame(pickRandomSteamGame());
            },
            pause: () => {
                clearTimeout(activeTimeout);
                enterRestBreak();
            },
            current: () => (isResting ? "RESTING (2-min break)" : currentGame),
            history: () => Array.from(playedHistory),
            stop: () => {
                clearTimeout(activeTimeout);
                clearGame();
                if (originalGetRunning) runStore.getRunningGames = originalGetRunning;
                if (originalGetGameForPID) runStore.getGameForPID = originalGetGameForPID;
                console.log("[SteamDB Auto-Plugin] Stopped.");
            }
        };
    }

    if (document.readyState === "complete") {
        start();
    } else {
        window.addEventListener("load", start);
    }
})();
// === END VENCORD 24/7 STEAMDB GAME BADGE SPOOFER ===
