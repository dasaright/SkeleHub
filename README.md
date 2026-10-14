# Skelefarm Hub — v0.2.1 test build

A Windows hub for launching selected Guild Wars accounts and coordinating leader/follower skeleton farms. Includes the supplied GwAu3 API snapshot and account-launching code adapted from Encounter ReBuilt PUBLIC.

This source build has passed automated Python and static source checks. **It has not been compiled or run against Guild Wars here.** First verify party assembly, then test one supervised farm when event captures are available.

## Launch from source

1. Extract the complete source folder to a writable location.
2. Install Python 3.11+ with Tkinter and AutoIt 3.3.16.1+ (32 bit).
3. Run `Start-Hub.cmd` and accept the administrator prompt. Under **Paths**, select the 32-bit `AutoIt3.exe` if its default path is different.
4. Click **Import characters.ini** and choose your existing local file. Imports character names and executable paths, without copying email addresses or passwords into the hub's settings.
5. Double-click each account to choose its team, Leader/Follower role, launch mode, `Gw.exe`, and `Gw.dat`. Browse buttons are included. Selecting `Gw.dat` finds its sibling `Gw.exe` when present.
6. Select the accounts to run and click **Launch selected accounts**. Only selected accounts start. Include exactly one designated leader per selected team. A launch session's team roster consists of those selected accounts.

### GW executable and Dat selection

Use the `Gw.exe` and `Gw.dat` from the **same installation folder**, matching the working farm's executable-based installation selection. Selecting a Dat file selects that installation; the hub does not copy, rename, or relink large Dat files. A custom-named Dat in an unrelated folder is not treated as a supported GW1 command-line switch.

### Account launch modes

| Mode | Behavior |
|---|---|
| Direct | Reads the chosen character section from the local `characters.ini`, decrypts its password in the worker, launches GW suspended, applies the supplied multiclient patch, resumes it, tracks its playable process, then attaches the farm. |
| Attach | Attaches to a character you have already logged in. |
| Profile | Uses the earlier GW Launcher's `-launch "profile"` interface; configure the external launcher under Paths. |

Direct mode reuses a character that is already logged in. The launcher uses `Email`, `Pwd`, and `FilePath`, with the account editor's executable override. It passes the account's character name with the login arguments, as Encounter does.

The supplied farm encrypts `{SEC}` passwords using its script filename. The default seed is `Encounter_ReBuilt.au3`, with a fallback to `Encounter_ReBuilt.exe`; if your original script was renamed when it saved passwords, enter that exact filename in **Original encryption script name**. Plaintext passwords are also accepted by the local launcher for compatibility. The hub never rewrites the original INI.

Passwords are read only by the Windows worker and passed to GW through the same command-line login mechanism as the supplied farm. They are not placed in the hub settings, session INIs, logs, repository, source package, or release ZIP. Keep your actual `characters.ini` outside the repository. The file is excluded by `.gitignore` as an additional safeguard.

## Test assembly before farming

**Assembly only** is enabled by default. All selected characters need ToA unlocked, an Everlasting Mobstopper in carried bags, one empty carried slot, and the farm build's skills unlocked.

1. Put two configured characters in different towns/districts.
2. Keep their team in **Assembly only** under **Team settings**. Default destination: Temple of the Ages, International district 1, language ID 0.
3. Select both, including the designated leader, and launch.
4. Verify they travel to the same district, the configured leader invites, and followers accept that leader.
5. The leader should show **Assembly verified — assembly-only mode**. No UW entry payment occurs.
6. Test Pause, Resume, Stop, and closing/reopening the hub.

The leader verifies live character login numbers, connectivity, exact roster, and leader identity. Heroes/henchmen and unconfigured players do not satisfy readiness. Town, region, language, and district must all match. These are local-PC teams; cross-machine coordination is not implemented.

## Farm mode and controls

Stop the team, select **Farm** under Team settings, and relaunch the selected roster. The leader follows the original ToA route and Grenth dialogue sequence. Each worker uses the original farm skill order with cast pacing and bounded waits. Success requires an actual increase in captured skeletons in that character's inventory. The leader waits for same-cycle completion before the party resigns and returns.

The leader needs 1,000 gold per entry. A bounded storage-gold withdrawal is attempted if necessary; have sufficient carried gold for your first test. Event availability, Grenth access, map signatures, combat timing and simultaneous capture behavior still require live confirmation.

- **Pause teams:** finish the current farm, return, and pause in the outpost.
- **Resume teams:** continue with the same session roster.
- **Stop teams:** stop workers, restore rendering, and leave GW clients open. Return manually if stopped inside UW.
- **Close hub:** leave active workers running. Reopening reconnects to their saved session registry.
- **Attention:** fix the reported issue, stop the team, and relaunch. No repeated paid entries or automatic crash-restart loop.
- **Open logs:** open local session logs. Logs rotate at approximately 5 MiB.

Team commands affect all workers in the selected rows' active teams. Team configuration is frozen while running. Statistics reset with workers; captures/hour includes elapsed waiting/paused time.

Original template: `OwNS44PTceTQmE4O2kxkRQYh` (A/Mo). Its slots are Shadow Sanctuary (Luxon), Dash, Signet of Judgment, Death's Charge, You Move Like a Dwarf!, Finish Him!, Unseen Fury, Smoke Powder Defense. The old `protspirit` variable name did not match its actual template; this worker validates the exact eight original skill IDs.

## Check for Update / Update Now

**Check for Update** queries the latest stable GitHub release at `dasaright/SkeleHub` in the background. Network errors and a repository without a published release produce a visible status message.

When a newer release with `SkeleHub-VERSION-windows.zip` is available, **Update Now** enables beneath it. Clicking downloads the package, checks its supplied SHA-256 digest when GitHub provides one, validates ZIP entries, then starts an independent replacement helper. The helper confirms startup before the hub closes, waits for the old hub to exit, retries temporarily locked files, backs up replaced files, applies the update, and starts the hub again. Failure to start the helper leaves the current hub open. It attempts rollback if replacement fails. Settings and session state stay in `%LOCALAPPDATA%\SkelefarmHub`.

Worker binaries are named `Skelefarm-worker-VERSION.exe`. An update installs a new worker filename instead of replacing a running worker. Existing workers and GW clients keep running; new launches use the updated worker. Stop/relaunch a team when you want that team to adopt the new worker. Old worker files are retained.

Updating a source-run hub installs and restarts the compiled hub in that folder. It does not rewrite the source checkout. `Start-Hub.cmd` prefers the compiled hub when present.

**An actual published Windows release is required.** These buttons do not compile an executable from raw GitHub source. Administrator access and a writable installation folder are required. Windows replacement/restart behavior still needs a supervised Windows test.

## Build executables and release package

Run on Windows with Python and AutoIt installed:

```powershell
powershell -ExecutionPolicy Bypass -File .\Build-Windows.ps1
```

For another AutoIt installation, add `-AutoItDir 'C:\YourPath\AutoIt3'`.

The script runs Au3Check and Python tests, compiles the x86 worker, installs PyInstaller, builds the hub, and creates `SkeleHub-0.2.1-windows.zip`. The portable package contains only:

- `Skelefarm Hub.exe`
- `Skelefarm-worker-0.2.1.exe`
- `README.md`
- `AUDIT.md`

Keep both executables together; launch and pin the hub to the taskbar. The target PC does not require Python or AutoIt once the binaries are built successfully.

The included Windows release workflow builds on main pushes and `v*` tags, verifies explicit tags against `version.py`, and publishes a new version only if checks and compilation pass. Existing versioned releases remain unchanged; increment `VERSION` for a new release. Manual workflow runs produce a downloadable Actions artifact without publishing a release. The workflow has not run successfully yet in this development session.

## Validation and scope

27 Python/static checks pass locally; two additional Windows-only tests exercise real replacement/restart and rollback using harmless temporary executables. The Windows CI runs all 29 checks. Tests cover configuration, credential exclusion, Unicode account import, Dat installation validation, selected roster snapshots, INI transport, stale status files, API names/control blocks, release selection, version comparisons, and rejecting malformed/unexpected update ZIP contents. Python syntax checks also pass.

Unavailable here: Windows GUI, AutoIt compilation, launcher/decryption behavior on Windows, current game memory offsets, combat, and actual binary replacement/restart. A passing Python test suite does not establish that the farm is live-ready.

The original attachments and turn-in script are unchanged. Automatic turn-in and cross-PC teams are outside this version. See `AUDIT.md` for the original repairs and source provenance.
