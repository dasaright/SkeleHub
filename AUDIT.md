# Skelefarm audit and implementation notes

## Findings in the uploaded Skelefarm

| Finding | Effect | Replacement behavior |
|---|---|---|
| Includes `..\gwApi\_gwApi.au3` and an absent `AccountInfo.au3` | Not runnable against the supplied GwAu3 package as-is | Bundled GwAu3 include and hub-generated session configuration |
| Mixed old and new API names | Many calls are unavailable in GwAu3 | Calls use the supplied API's current function definitions |
| Reads `$CmdLine[2]` and `[3]` whenever any argument exists | Argument-array bounds failure | Named `--session` / `--account` arguments validated |
| Automatic startup sets running before verifying initialization | Possible game operations without a valid attachment | Exact-character initialization required |
| Fixed party size 6 and hard-coded invite names | No configurable teams or reliable leader designation | 1–8 configured accounts, exactly one designated leader |
| Every account that happens to be party leader can invite/zone | Competing parties and races | Only the configured leader invites and requests entry |
| No follower-side explicit invite acceptance | Assembly can stall | Followers accept only the designated leader's live party ID |
| Party size is the primary readiness check | Wrong players can satisfy size | Compare live login numbers, connectivity, exact roster, and leader identity |
| Travel helper can ignore district changes | Same town but different districts | Explicit map/region/language/district check and `Map_MoveMap` |
| Compares timer handles to 3000 / 20000 | Intended waits do not time out correctly | `TimerDiff` and bounded state timers |
| Multiple indefinite loops for party, Grenth, loading, and target HP | Bot can hang silently | Deadline followed by visible attention state |
| No robust missing/dead target guard | Invalid skill/HP/item operations | Validate target and stop the attempt when invalid |
| Very short delays between skill calls | Queued casts can replace one another | Activation/aftercast pacing and casting checks |
| Calls capture even when the target is dead | False capture attempt | Capture while the live target is below the health threshold |
| Reports capture unconditionally; survival defines success | Misleading success statistics | Count capture only when inventory quantity increases |
| Early captures can resign before slower teammates finish | Followers may lose their capture | Same-cycle done barrier before resignation |
| Divides by rounded hours early in a session | Division by zero | Minimum elapsed-time denominator |
| Disconnect handler kills Guild Wars | Client/account state lost | Visible attention state; clients remain open |
| Slot 1 named `protspirit` despite template skill 1948 | Misleading maintenance assumptions | Decode and validate the actual original template |

The farm route, dialogue IDs, and overall skill order are retained from the supplied worker. The GUI and coordination loop were rewritten rather than patched around the old account framework.

## Architecture

The hub launches one x86 AutoIt process per character. Each launch writes a new immutable team snapshot and one command file per account. Each worker publishes its own status file using a temporary-file replacement. The hub is the only command writer; workers never write each other's status files.

Each worker reports a timestamp and PID. Peers reject absent, stale (>10 seconds), paused, errored, or stopped workers. The leader waits for exact membership and follower readiness. Live district-local login numbers identify party members. Accepting an invitation uses the configured leader's published party ID. Run cycles prevent a prior run's done state from satisfying the current completion barrier.

Pausing is a team command and occurs in an outpost. Stopping restores rendering and exits the worker. Workers survive hub closure. The hub reuses its saved session registry on restart. There is no network coordinator, copied account-password store, aggressive restart loop, or turn-in automation in this version. Version 0.2 adds a release updater as described below.

## API and model provenance

- Supplied archive: `GwAu3.zip`.
- Archive repository HEAD: `147ddb50f31869c61c073ab6ae7b924e5a3b7140`. The archive contains local modifications; bundled bytes follow the archive rather than claiming to be a pristine checkout of that commit.
- Upstream metadata and README checked through GitHub: https://github.com/GwAu3-Projects/GwAu3
- Legacy NPC model constants checked through GitHub in `logan-77/gwApi`, `constants/agent_model_id.au3`, indexed commit `454affc21e8421a3c5d23114596292fa9efc1b52`: Avatar of Grenth 1995; Skeleton of Dhuum variants 2392 and 2393. https://github.com/logan-77/gwApi/blob/454affc21e8421a3c5d23114596292fa9efc1b52/constants/agent_model_id.au3
- Current bundled GwAu3 constants: Everlasting Mobstopper 32558, captured skeleton 32559; Temple of the Ages 138 and UW 72.
- Original template decoded as A/Mo, 12 Shadow Arts and 12 Smiting Prayers, skill IDs `[1948,1043,294,952,2358,2353,1041,2136]`.

The NPC constants and original dialogue/route still need live confirmation. No latest-upstream compatibility or live farm performance claim is made. Game updates may require newer signatures/API changes, which should be tested as a coordinated version change rather than allowing each account to self-update independently.

## Local validation limits

Python was checked on Linux. Windows, AutoIt/Au3Check, and Guild Wars were unavailable. Included tests are static and configuration/transport tests, not a simulation of the game or a substitute for Windows compilation. Windows build script and supervised test sequence are in README.md.


## Version 0.2 account launch and updates

`launcher/AccountLaunch.au3` adapts only the account-launch, argument-quoting, multiclient-patch and playable-PID/job tracking functions from the newly supplied Encounter ReBuilt PUBLIC archive. `AccountSecurity.au3` adapts its password decryption and local file mutex helpers. Original authors KleuTSchi and Greg are credited in source. No character file or other farm configuration is copied into the project.

Changes from the reference launcher: remove email logging; accept the configured executable override; preserve original encryption seed compatibility; reject failed decryption; reject a missing patch signature before touching memory; include the final possible signature match; flush the instruction cache after patching; terminate a newly created suspended child on setup failure; and bound playable-window tracking at 120 seconds. Game patcher replacement behavior still follows the reference implementation and needs live testing after game updates.

The hub imports only character names and filesystem references. The original local INI remains authoritative for credentials. Executable and Dat selectors address one installation folder, matching the reference's executable-based data selection. Launch snapshots include only selected accounts, with one leader required in each selected team.

The updater downloads only the expected release asset from this repository, checks the API-provided digest when available, rejects extra files/path traversal/links/oversized packages, and stages replacement outside the installation. A separate helper waits only for the hub PID. Versioned worker names preserve the binaries of running workers. Replacement failures attempt rollback. No credentials or settings are included in a release package.

Current tests: 23 passing Python/static checks. Current limitations: no Windows compilation, GUI, live login/decryption, farming, or actual update/restart execution available in this environment. Source publication was approved. The user made the repository public and explicitly approved public source publication.


## Version 0.2.1 updater review

Confirmed SkeleHub is public and the initial source-check workflow passed. No Windows release existed at the time of review. Added a helper-ready handshake, cancelled-handoff guard, replacement retries, reverse-order rollback, and a persisted result for the next hub startup. The updater leaves current workers and their versioned executables untouched.

Added tests for full release download/staging, digest rejection, incomplete download cleanup, helper readiness/failure, and real Windows replacement/restart plus rollback with isolated temporary test programs. Local result: 27 passing, two Windows tests skipped because this environment is Linux. CI runs the two additional Windows tests. The Windows workflow now creates a release for a new VERSION after successful main/tag builds; existing releases are not overwritten.
