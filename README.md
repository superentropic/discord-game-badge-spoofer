# discord-game-badge-spoofer

a simple tool and vencord plugin to help get the new discord game badges (game time & game variety) by playing real games from steamdb.

---

### what does it do?
- pulls 19,000+ real games from steamdb and discord's game list
- picks a random game and plays it for 20 minutes
- goes offline for 2 minutes so discord registers the game session
- picks another random game and repeats forever
- works in the background automatically

---

### how to use it in vencord / vesktop

#### option 1: vencord plugin (recommended)
1. copy the `vencord-plugin` folder to your vencord source:
```bash
cp -r vencord-plugin /path/to/Vencord/src/plugins/steamDbBadgeSpoofer
```
2. build vencord:
```bash
pnpm build
```
3. restart or reload discord (`ctrl + r`). it will show up in vencord settings > plugins and run automatically!

#### option 2: quick console paste (no building needed)
1. press `ctrl + shift + i` in discord / vesktop to open console.
2. type `allow pasting` and press enter if asked.
3. copy everything inside `steamdb_vencord_plugin.js` and paste it.

---

### console controls
open console (`ctrl + shift + i`) anytime to control it:
- `window.__badgeSpoofer.next()` — skip to next random game right now
- `window.__badgeSpoofer.current()` — see what game is playing and its steamdb link
- `window.__badgeSpoofer.pause()` — take a 2-minute break right now
- `window.__badgeSpoofer.stop()` — stop the spoofer

or use the discord chat command:
- `/spoofer` — check current status and games history

---

### python standalone runner (optional)
if you want to run it as a standalone python program instead:
```bash
# run any game by steamdb link
python3 launcher.py --app https://steamdb.info/app/1091500/

# or run the 24/7 background service
python3 vencord_daemon.py start
python3 vencord_daemon.py status
python3 vencord_daemon.py stop
```

---

### settings check
make sure in discord settings:
1. go to **user settings > activity privacy**
2. turn ON **"display current activity as a status message"**
3. turn ON **"share your detected activities with others"**
