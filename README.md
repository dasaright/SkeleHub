# Skelefarm Hub / Python SkeleBot — v0.3.0

A Windows Python hub and Python farm controller for selected Guild Wars accounts. The desktop uses EncounterHub's PySide6 implementation pattern and the same charcoal/teal stylesheet, checkboxes, per-row controls, and saved column widths.

## Current scenario: combat test

Combat test is enabled automatically once when moving to this version. It preserves Farm and Assembly-only modes under **Team Settings**.

1. Selected characters travel to the same Temple of the Ages town, region, language, and district.
2. The configured leader forms the exact selected team. Followers accept that leader.
3. The leader runs to the Grenth statue, kneels, and requests UW entry.
4. Accounts wait for the team to load UW, move to the Skeleton of Dhuum, and kill it using the original build/skill sequence plus normal attacks.
5. Each worker verifies the skeleton is dead, waits **two seconds**, then resigns.
6. **Every account repeatedly requests return to town**, regardless of current in-game leadership, until it confirms Temple of the Ages is loaded as an outpost.
7. Accounts regroup under the designated leader, which attempts the next UW entry.

Combat test ignores Everlasting Mobstopper and inventory-space requirements. It never invokes capture or counts kills as captured skeletons. The leader still needs 1,000 gold per entry and working Grenth access. A vanished target alone does not count as a confirmed death. Timeouts produce an attention state.

Stop/relaunch a team to move existing workers onto the new Python controller and combat-test mode. Updating the hub leaves existing workers running their original version until you restart them.

## Rendering and controls

Each row has **Select**, character/team/role, live status, **Disable Rendering**, Pause, Resume, Stop, Launch, and statistics. Column widths can be resized and are saved; **Fit Columns** resets the layout.

**Disable Rendering** is a live checkbox and a saved account preference. It follows Encounter ReBuilt's implementation: compare the requested setting with `Ui_GetRenderDisabled()`, then use `Ui_ToggleRendering()` only when they differ. Disabling also hides the GW window and clears memory; enabling shows it again. Worker cleanup restores rendering and shows its client.

Rendering changes preserve pause/run state. Pause/Resume/Stop row buttons act on that account's team; coherent team behavior prevents one paused account from being left behind. Launch on a single follower row requires selecting its leader as well through **Launch Selected**.

- **Pause:** finish the current run, then wait in an outpost.
- **Resume:** resume assembly/entry using the same session roster.
- **Stop:** stop workers and restore rendering; game clients stay open.
- **Close hub:** workers remain running. Reopening reconnects through saved session files.
- **Update Now:** restarts only the hub; existing workers and clients stay running.

## Architecture and preserved logic

`worker.py` owns the complete farm state machine, timing, team identity, supplies, combat, capture verification, statistics, resignation and return behavior. `desktop.py` is the PySide6 GUI. `controller.py` shares account/settings/session handling independently from the GUI layout, mirroring EncounterHub's controller reuse.

GwAu3 is an AutoIt API. `GwAu3Bridge.au3` is a thin x86 adapter exposing game reads/actions over an authenticated loopback connection. It contains no farm loop or farm timing. The Python worker controls it. Compiled releases embed this adapter inside the Python worker executable; no extra interpreter is required on the target PC.

The old AutoIt farm is retained under `legacy/` as a reference and is not compiled or launched. Native account launching still uses the supplied Encounter ReBuilt's suspended-process launch, multiclient patch, encrypted INI reads and playable-process tracking. The actual farm decisions are Python.

**Farm** mode retains Mobstopper and free-slot validation, original skill IDs, inventory-verified captures, follower-completion coordination and leader return behavior. **Assembly only** stops after verified party formation without paying for UW entry.

Original A/Mo template: `OwNS44PTceTQmE4O2kxkRQYh`. Slots: Shadow Sanctuary (Luxon), Dash, Signet of Judgment, Death's Charge, You Move Like a Dwarf!, Finish Him!, Unseen Fury, Smoke Powder Defense.

## Accounts, executables and Dat files

1. Import your local **characters.ini**.
2. Edit each account's team, Leader/Follower role, launch mode, GW executable and Dat file.
3. Choose `Gw.exe` and `Gw.dat` from the same installation folder. Browsing to a Dat selects the sibling executable when present. Large Dat files are never copied or relinked.
4. Select the accounts to launch, including exactly one leader per selected team. Only selected accounts form the launch roster.

**Direct** mode reads the local INI's `Email`, `Pwd`, and `FilePath`. It supports Encounter's `{SEC}` encryption, defaulting to `Encounter_ReBuilt.au3` and falling back to `Encounter_ReBuilt.exe`; enter the exact original encryption filename if yours was renamed. **Attach** uses an already logged-in character. **Profile** uses the earlier external GW Launcher's `-launch` interface.

The original local INI is never rewritten. Passwords/email addresses are not copied into settings, session files, logs, source, or releases. Login uses the same command-line mechanism as the supplied working farm. Keep `characters.ini` outside the repository; `.gitignore` also excludes it and Dat files.

Settings, selected rows, rendering preferences, column widths, session registries and logs live under `%LOCALAPPDATA%\SkelefarmHub`. Logs rotate at approximately 5 MiB. Accounts on one Windows PC are supported; cross-PC teams and skeleton turn-in are not implemented.

## Run from source

Install Python 3.11+ and 32-bit AutoIt 3.3.16.1+, then:

```powershell
py -3 -m pip install -r requirements.txt
```

Run `Start-Hub.cmd` and accept administrator elevation. Set the x86 `AutoIt3.exe` path under **GW Paths** if needed. The desktop and farm run in Python; the source bridge runs through AutoIt.

## Executables, updates and releases

Keep these together:

- `Skelefarm Hub.exe`
- `Skelefarm-worker-0.3.0.exe`

The Python worker embeds its versioned x86 bridge. Target PCs need neither Python nor AutoIt once built. Pin the hub executable to the taskbar.

**Check for Updates** reads the public GitHub release feed. **Update Now** downloads the matching `SkeleHub-VERSION-windows.zip`, verifies its digest when supplied, rejects unexpected ZIP contents, confirms the helper started, then closes the hub. A separate helper waits for it to exit, retries temporary file locks, replaces files with backups, and restarts the hub. Failure attempts rollback. Settings and credentials are never replaced.

Versioned workers prevent replacing an active binary. This package stays compatible with the v0.2.1 updater: the adapter is embedded, so the portable ZIP still contains only the hub, versioned worker, README and audit.

Build on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\Build-Windows.ps1
```

Add `-AutoItDir 'C:\YourPath\AutoIt3'` for another installation. Builds run AutoIt checks on the native bridge, Python/Qt/Windows tests, compile the bridge, package the Python worker and Qt hub, and create the release ZIP. Main pushes/tags build and publish a new VERSION only after success; existing releases are not overwritten. CI verifies the public release download using the real updater code.

## Validation limits

The v0.2.1 updater passed all 29 Windows checks, real replacement/restart and rollback tests with an independent worker left running, and a public download/checksum/package validation check.

Version 0.3 adds Python farm-scenario tests and a Qt desktop smoke test. Live game behavior, combat/build suitability, current memory signatures and repeated UW entry require supervised in-game testing. Begin with two accounts. These changes do not claim a completed live farm test.
