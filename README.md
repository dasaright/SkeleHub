# Skelefarm Hub / Python SkeleBot — v0.4.2

A Windows Python hub and Python farm controller for selected Guild Wars accounts. The desktop uses EncounterHub's PySide6 implementation pattern and the same charcoal/teal stylesheet, checkboxes, per-row controls, and saved column widths.

## Upgrading from versions 0.3.0 through 0.3.7

Those versions contain a Qt/Tk button API mismatch that prevents the update buttons from working. Close the hub, download the v0.3.8 Windows ZIP from GitHub Releases, extract it into the existing installation folder replacing the hub executable, and start the replaced executable. Local settings and accounts remain under LOCALAPPDATA and are preserved. Version 0.3.8 fixes both update buttons; subsequent updates can use the hub. Tests now click the actual Qt buttons through checking, download failure/retry, and helper handoff.

## Leader funding and rotation

Funding rotation is enabled in Team Settings. At ToA, the current party leader withdraws only the amount needed to reach 20 carried platinum (or the remaining storage balance if smaller). With no storage gold, it continues leading while carrying at least 5 platinum. Below 5, it reports **Empty on Plat** and hands the leader role to a funded follower. The controlled funding rotation reforms the party under that account and verifies the resulting party leader. Ordinary party-order changes retain the complete party. After every account is exhausted, the team waits for turn-in mode.

New columns show carried platinum, storage platinum, available Captured Skeletons, and funding state. Currency is tracked separately for each account. Session funding/turn-in state survives worker recovery.

## Handle Currency test buttons

Each account has **Handle Currency**, and the bottom toolbar has **Handle Currency Selected**. Launch accounts first. A request waits until the account is in an outpost, leaves the party, visits Eye of the North/Roland, requests quotes and exercises the existing currency policy, then returns to the configured ToA district. It works with funding rotation and seasonal turn-ins disabled and preserves Pause. Teammates wait while the account is away. Repeated clicks are coalesced rather than restarting a pending purchase.

This test never sends seasonal quest dialogs or consumes skeletons. It counts skeleton value toward the existing 800–900 platinum limits, so it can visit and obtain a quote without buying when the policy calls for no purchase. It does not force a purchase below the configured valuation band.

## Seasonal Turn In Mobs — implemented, not live tested

**Enable seasonal turn-ins** in Team Settings is **No by default**. Leave it off until the quest NPC is available. No quest dialogs or ectoplasm purchases are sent while disabled. Combat Test and Farm remain separate: choose Farm when you want actual captures; Combat Test kills do not generate Captured Skeletons.

When enabled and all accounts are Empty on Plat, each character leaves the party and independently travels to Lion's Arch. The reference script supplies the NPC location (5267, 9070), dialogs `0x846303`, `0x846301`, `0x846307`, and alternating districts 1/2. The worker checks both skeleton consumption and ToT bag receipt, banks ToT bags into existing stacks/free storage slots, deposits gold, and changes district before repeating. It stops rather than blindly repeating an unconfirmed reward or deposit.

Valuation uses **inventory gold + storage gold + floor(Captured Skeletons / 3) × 1,000 gold**. Once storage exceeds 800 platinum and that value exceeds 900, the character travels to Eye of the North, locates Roland by name, obtains fresh quotes, and buys ectoplasm one at a time. Each purchase must increase ectoplasm and decrease gold before another is sent. It stops in the 800–900 platinum band when attainable. If the skeleton value alone exceeds 900, it spends liquid gold until it cannot afford the next quote, then resumes Lion's Arch turn-ins and repeats when storage builds up again. Ectoplasm is retained in inventory and is not counted as liquid platinum.

With 0–2 skeletons left, each account returns to the configured ToA district. The team waits for everyone to finish, clears Empty on Plat flags, reassembles, and resumes farming. Missing seasonal NPCs, unreachable trader, full storage/inventory, stale quotes or unconfirmed transactions produce an Economy Hold instead of an account restart loop. Worker recovery resumes the persisted stage. Starting a new team session reassesses current inventories. NPC interaction, paths, gold access and trading require supervised live testing once available.

Source references: uploaded Skele turn-in script; GwAu3 item/merchant APIs; [Roland](https://wiki.guildwars.com/wiki/Roland); [party leadership on leaving](https://wiki.guildwars.com/wiki/Party).

## Death's Charge and party retention

Each account must request Death's Charge and observe its recharge plus arrival within 300 units of the skeleton before continuing immediately to Smoke Powder Defense (slot 3), Unseen Fury (slot 7), and Signet of Judgment (slot 4). A request alone or a pre-existing cooldown does not count. Smoke Powder Defense also waits for its own cast confirmation before Signet can proceed; town preparation waits for its recharge. Unaccepted casts retry up to three times; an unsuccessful approach returns to town rather than casting the damage sequence at range.

A complete team is verified by connected character login numbers, independent of party order and leader. The current in-game party leader handles UW entry and run numbering; the configured leader remains the assembly anchor for split teams. A change of party leader hands entry off without leaving a complete party.

## Template and combat consistency

`farm_build.py` is the single source for the current template `OwNS44PTTQ4OYhmE2kxkRQAA` and its seven occupied slots. The template loads and verifies once when the character initializes, before the first town travel. Ordinary town returns check supplies and recharge without reloading or revalidating the template. Status files include worker version, template, skill IDs and attempt count; logs record observed attributes and skills for load attempts.

Leader and followers share the same targeting, cast sequence, repeat-damage loop and normal attacks. Each receives a full combat timeout after the team readiness barrier clears, so the leader's earlier loading time does not shorten its fight.

## Recovery and UW readiness

The hub dismisses Don't Send crash-report buttons only for tracked Guild Wars processes or configured active game executable paths. External Windows Error Reporting dialogs must include the configured game path. It retries failed accounts up to three times per session, waits for the old worker to exit before relaunching, and respects manual Stop/Pause. Persistent configuration errors remain stopped after the retry limit.

A fully loaded UW map now takes precedence over stale town/travel/preparation phases. Readiness verifies connected party login numbers against locally visible player agents in the current UW instance. Run counters are diagnostic labels and never block a loaded team.

## Shared status reliability

Session writes retry transient Windows sharing locks for up to two seconds. Worker logs retain the actual exception traceback; a file permission failure is reported separately from game communication. UW readiness names accounts still loading or needing attention. If a teammate worker fails, loaded accounts wait ten seconds, then return to town rather than remaining silently blocked.

## Startup and shutdown

Workers stop when the hub closes, including an update restart. New workers also monitor the hub PID so an unexpected hub exit stops them. After loading the configured character, each worker enables Disable Rendering, leaves any previous party, and confirms party departure before travel and assembly. Rendering can then be toggled manually. The template is `OwNS44PTTQ4OYhmE2kxkRQAA`; slot 8 is empty and is skipped during combat.

## Character selection and build checks

Version 0.3.8 follows Encounter ReBuilt's selection sequence: attach to the newly launched playable client PID, wait for character selection, send N, search right for the configured character (up to 20 slots), then press Enter. It confirms the actual loaded character and waits for outpost/profession data before travelling. Missing or wrong characters stop with an attention message.

The original farm template is loaded in the outpost after confirming Assassin primary. The worker verifies Monk secondary, 12 base Smiting Prayers, 12 base Shadow Arts and all eight slot values (including the empty eighth slot). It allows 15 seconds for updates and at most three load attempts before reporting unavailable professions, attributes or skills. Live game verification is still required.

## Current scenario: combat test

Combat test is enabled automatically once when moving to this version. It preserves Farm and Assembly-only modes under **Team Settings**.

1. Selected characters travel to the same Temple of the Ages town, region, language, and district.
2. The configured leader forms the exact selected team. Followers accept that leader.
3. The current in-game party leader runs to the Grenth statue, kneels, and requests UW entry.
4. Accounts wait for the team to load UW, move to the Skeleton of Dhuum, and kill it using the original build/skill sequence plus normal attacks.
5. Each worker verifies the skeleton is dead, waits **two seconds**, then resigns.
6. **Every account repeatedly requests return to town**, regardless of current in-game leadership, until it confirms Temple of the Ages is loaded as an outpost.
7. Accounts retain the complete team regardless of party order; the current in-game party leader attempts the next UW entry.

Combat test ignores Everlasting Mobstopper and inventory-space requirements. It never invokes capture or counts kills as captured skeletons. The leader still needs 1,000 gold per entry and working Grenth access. A vanished target alone does not count as a confirmed death. Timeouts produce an attention state.

Stop/relaunch a team to move existing workers onto the new Python controller and combat-test mode. Closing or updating this hub stops its workers and restores game rendering. Game clients stay open. Relaunch the selected team after restarting the hub.

## Rendering and controls

Each row has **Select**, character/team/role, live status, **Disable Rendering**, Pause, Resume, Stop, Launch, and statistics. Column widths can be resized and are saved; **Fit Columns** resets the layout.

**Disable Rendering** is a live checkbox and a saved account preference. It follows Encounter ReBuilt's implementation: compare the requested setting with `Ui_GetRenderDisabled()`, then use `Ui_ToggleRendering()` only when they differ. Disabling also hides the GW window and clears memory; enabling shows it again. Worker cleanup restores rendering and shows its client.

Rendering changes preserve pause/run state. Pause/Resume row buttons act on the account's team. Stop on a row closes only that account's client and worker; Stop Teams closes all accounts in the selected teams. Launch on a single follower row requires selecting its leader as well through **Launch Selected**.

- **Pause:** finish the current run, then wait in an outpost.
- **Resume:** resume assembly/entry using the same session roster.
- **Stop:** close the targeted game client and worker.
- **Close hub:** stop all workers and restore rendering; game clients stay open.
- **Update Now:** stops workers, restarts the hub, and leaves game clients open. Relaunch the team afterward.

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

Settings, selected rows, rendering preferences, column widths, session registries and logs live under `%LOCALAPPDATA%\SkelefarmHub`. Logs rotate at approximately 5 MiB. Accounts on one Windows PC are supported; cross-PC teams are not implemented. Seasonal turn-ins and trader purchases are implemented but intentionally disabled pending live NPC testing.

## Run from source

Install Python 3.11+ and 32-bit AutoIt 3.3.16.1+, then:

```powershell
py -3 -m pip install -r requirements.txt
```

Run `Start-Hub.cmd` and accept administrator elevation. Set the x86 `AutoIt3.exe` path under **GW Paths** if needed. The desktop and farm run in Python; the source bridge runs through AutoIt.

## Executables, updates and releases

Keep these together:

- `Skelefarm Hub.exe`
- `Skelefarm-worker-0.4.2.exe`

The Python worker embeds its versioned x86 bridge. Target PCs need neither Python nor AutoIt once built. Pin the hub executable to the taskbar.

The bottom-left status message shows release checks, download percentage and MB, checksum/package validation, extraction, helper startup, restart, and the result after reopening. Helper startup runs off the UI thread.

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
