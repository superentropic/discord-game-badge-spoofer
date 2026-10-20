/*
 * Vencord, a modification for Discord's desktop app
 * Copyright (c) 2024 Vendicated and contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

import { ApplicationCommandInputType, sendBotMessage } from "@api/Commands";
import { definePluginSettings } from "@api/Settings";
import definePlugin, { makeRange, OptionType } from "@utils/types";
import { findByProps } from "@webpack";
import { FluxDispatcher, RunningGameStore } from "@webpack/common";

const settings = definePluginSettings({
    playDuration: {
        description: "Minutes to play each Steam game before taking a break (default: 20)",
        type: OptionType.SLIDER,
        markers: makeRange(5, 60, 5),
        default: 20,
        stickToMarkers: false
    },
    restDuration: {
        description: "Minutes to stay offline between games (default: 2)",
        type: OptionType.SLIDER,
        markers: makeRange(1, 10, 1),
        default: 2,
        stickToMarkers: false
    }
});

interface SteamGameItem {
    name: string;
    appId: string;
    steamdbUrl: string;
    exeName: string;
}

let activeTimer: any = null;
let currentGame: any = null;
let isResting = false;
const playedHistory: Set<string> = new Set();
let cachedGames: SteamGameItem[] = [];

let originalGetRunning: any = null;
let originalGetGameForPID: any = null;

function shimNative() {
    if (!(window as any).DiscordNative) (window as any).DiscordNative = {};
    if (!(window as any).DiscordNative.nativeModules) {
        (window as any).DiscordNative.nativeModules = {
            requireModule: () => ({
                GetWindowFullscreenTypeByPid: () => 0,
                init: () => {},
                setOverlayCallback: () => {}
            }),
            ensureModule: () => Promise.resolve()
        };
    }
    const utilsMod = findByProps("getDiscordUtils") as any;
    if (utilsMod) {
        utilsMod.getDiscordUtils = () => ({ GetWindowFullscreenTypeByPid: () => 0 });
    }
}

async function fetchSteamCatalog(): Promise<SteamGameItem[]> {
    if (cachedGames.length > 0) return cachedGames;
    try {
        const res = await fetch("/api/v9/applications/detectable");
        const rawCatalog = await res.json();
        const games: SteamGameItem[] = [];
        for (const app of rawCatalog) {
            const steamSku = app.third_party_skus?.find((s: any) => s.distributor === "steam");
            if (steamSku?.id && app.name && app.id) {
                let exeName = "game.exe";
                if (app.executables?.length > 0) {
                    const best = app.executables.find((e: any) => !e.is_launcher && e.name) || app.executables[0];
                    if (best?.name) {
                        const n = best.name.startsWith(">") ? best.name.slice(1) : best.name;
                        exeName = n.split("/").pop().split("\\").pop();
                    }
                }
                games.push({
                    name: app.name,
                    appId: String(app.id),
                    steamdbUrl: `https://steamdb.info/app/${steamSku.id}/`,
                    exeName
                });
            }
        }
        cachedGames = games;
        console.log(`%c[SteamDB Auto-Plugin] Loaded ${games.length} SteamDB games!`, "color: #22c55e; font-weight: bold;");
        return games;
    } catch (e) {
        console.error("[SteamDB Auto-Plugin] Failed to fetch catalog:", e);
        return [];
    }
}

function pickRandomGame(games: SteamGameItem[]): SteamGameItem {
    if (games.length === 0) {
        return {
            name: "Counter-Strike 2",
            appId: "730",
            steamdbUrl: "https://steamdb.info/app/730/",
            exeName: "cs2.exe"
        };
    }
    return games[Math.floor(Math.random() * games.length)];
}

function clearCurrentGame() {
    if (currentGame) {
        FluxDispatcher.dispatch({
            type: "RUNNING_GAMES_CHANGE",
            added: [],
            removed: [currentGame],
            games: []
        });
        FluxDispatcher.dispatch({
            type: "LOCAL_ACTIVITY_UPDATE",
            socketId: null,
            pid: currentGame.pid,
            activity: null
        });
        currentGame = null;
    }
}

function launchGame(item: SteamGameItem) {
    clearCurrentGame();
    isResting = false;
    const pid = 50000 + Math.floor(Math.random() * 10000);

    const game = {
        id: item.appId,
        name: item.name,
        exePath: `/usr/games/${item.exeName}`,
        cmdLine: "",
        pid,
        pidPath: [pid],
        processName: item.exeName,
        start: Date.now(),
        windowHandle: 1,
        fullscreenType: 0,
        overlay: false,
        hidden: false
    };

    currentGame = game;
    playedHistory.add(item.name);

    FluxDispatcher.dispatch({
        type: "RUNNING_GAMES_CHANGE",
        added: [game],
        removed: [],
        games: [game]
    });

    FluxDispatcher.dispatch({
        type: "LOCAL_ACTIVITY_UPDATE",
        socketId: null,
        pid: game.pid,
        activity: {
            name: game.name,
            type: 0,
            timestamps: { start: game.start }
        }
    });

    console.log(
        `%c[SteamDB Auto-Plugin] 🎮 Playing: ${item.name} (${item.steamdbUrl})\n` +
        `  • Running for ${settings.store.playDuration} mins | History: ${playedHistory.size} titles`,
        "color: #38bdf8; font-weight: bold;"
    );

    clearTimeout(activeTimer);
    activeTimer = setTimeout(enterBreak, settings.store.playDuration * 60 * 1000);
}

function enterBreak() {
    isResting = true;
    clearCurrentGame();
    console.log(
        `%c[SteamDB Auto-Plugin] ☕ Resting for ${settings.store.restDuration} minutes before next game...`,
        "color: #a78bfa; font-weight: bold;"
    );

    clearTimeout(activeTimer);
    activeTimer = setTimeout(async () => {
        const games = await fetchSteamCatalog();
        launchGame(pickRandomGame(games));
    }, settings.store.restDuration * 60 * 1000);
}

export default definePlugin({
    name: "SteamDbBadgeSpoofer",
    description: "Automatically rotates real SteamDB games (20m play, 2m break) to unlock Discord game profile badges.",
    tags: ["Activity", "Utility"],
    authors: [{ name: "superentropic", id: 0n }],
    settings,
    enabledByDefault: true,

    commands: [
        {
            name: "spoofer",
            description: "Check status of SteamDB Badge Spoofer",
            inputType: ApplicationCommandInputType.BUILT_IN,
            options: [],
            execute: async (_, ctx) => {
                const status = isResting
                    ? `☕ Resting (break for ${settings.store.restDuration}m)`
                    : currentGame
                        ? `🎮 Playing: **${currentGame.name}** (Active for ${Math.round((Date.now() - currentGame.start) / 60000)}m)`
                        : "Inactive";
                sendBotMessage(ctx.channel.id, {
                    content: `**[SteamDB Badge Spoofer]**\n${status}\nTotal unique games played: **${playedHistory.size}**`
                });
            }
        }
    ],

    async start() {
        shimNative();

        if (RunningGameStore) {
            originalGetRunning = RunningGameStore.getRunningGames;
            originalGetGameForPID = RunningGameStore.getGameForPID;

            RunningGameStore.getRunningGames = () => (currentGame ? [currentGame] : []);
            RunningGameStore.getGameForPID = (pid: number) => (currentGame?.pid === pid ? currentGame : null);
        }

        const games = await fetchSteamCatalog();
        launchGame(pickRandomGame(games));

        (window as any).__badgeSpoofer = {
            next: async () => {
                clearTimeout(activeTimer);
                const list = await fetchSteamCatalog();
                launchGame(pickRandomGame(list));
            },
            pause: () => {
                clearTimeout(activeTimer);
                enterBreak();
            },
            current: () => (isResting ? "RESTING" : currentGame),
            history: () => Array.from(playedHistory),
            stop: () => {
                clearTimeout(activeTimer);
                clearCurrentGame();
            }
        };
    },

    stop() {
        clearTimeout(activeTimer);
        clearCurrentGame();
        if (RunningGameStore && originalGetRunning) {
            RunningGameStore.getRunningGames = originalGetRunning;
            RunningGameStore.getGameForPID = originalGetGameForPID;
        }
        delete (window as any).__badgeSpoofer;
    }
});
