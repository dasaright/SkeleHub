; Skelefarm worker v0.1 — rewritten from Skele Bot by Adon and Taco.
; Run through Skelefarm Hub. Requires x86 AutoIt and the bundled GwAu3 API.
#AutoIt3Wrapper_UseX64=n
#NoTrayIcon
#RequireAdmin
#include "vendor\GwAu3\API\_GwAu3.au3"
#include "launcher\AccountLaunch.au3"

; Pin the attached API: concurrent workers must never update shared source.
$g_b_AutoUpdate = False
Global $sfSession = "", $sfID = ""
For $sfArg = 1 To $CmdLine[0] - 1
    If $CmdLine[$sfArg] = "--session" Then $sfSession = $CmdLine[$sfArg + 1]
    If $CmdLine[$sfArg] = "--account" Then $sfID = $CmdLine[$sfArg + 1]
Next
If $sfSession = "" Or Not StringRegExp($sfID, "^[a-zA-Z0-9]+$") Then
    MsgBox(16, "Skelefarm", "Launch this worker through Skelefarm Hub.")
    Exit 1
EndIf
Global $sfTeam = $sfSession & "\team.ini"
Global $sfCommand = $sfSession & "\" & $sfID & ".command.ini"
Global $sfStatus = $sfSession & "\" & $sfID & ".status.ini"
Global $sfLog = $sfSession & "\" & $sfID & ".log"
Global $sfCount = Int(IniRead($sfTeam, "Team", "Count", 0))
If $sfCount < 1 Or $sfCount > 8 Then Exit 2
Global $sfMembers[$sfCount][2], $sfIndex = -1
For $sfI = 0 To $sfCount - 1
    $sfMembers[$sfI][0] = IniRead($sfTeam, "Member" & ($sfI + 1), "ID", "")
    $sfMembers[$sfI][1] = IniRead($sfTeam, "Member" & ($sfI + 1), "Character", "")
    If $sfMembers[$sfI][0] = $sfID Then $sfIndex = $sfI
Next
If $sfIndex < 0 Then Exit 3
Global $sfCharacter = $sfMembers[$sfIndex][1]
Global $sfLeader = IniRead($sfTeam, "Team", "Leader", "")
Global $sfIsLeader = ($sfLeader = $sfID)
Global $sfRegion = Int(IniRead($sfTeam, "Team", "Region", -2))
Global $sfLanguage = Int(IniRead($sfTeam, "Team", "Language", 0))
Global $sfDistrict = Int(IniRead($sfTeam, "Team", "District", 1))
Global Const $SF_TOA = 138, $SF_UW = 72
Global Const $SF_MOBSTOPPER = 32558, $SF_CAPTURED = 32559
Global $sfGrenth = Int(IniRead($sfTeam, "Team", "GrenthModel", 1995))
Global $sfSkeleton1 = Int(IniRead($sfTeam, "Team", "SkeletonModel1", 2392))
Global $sfSkeleton2 = Int(IniRead($sfTeam, "Team", "SkeletonModel2", 2393))
Global $sfAssemblyOnly = Int(IniRead($sfTeam, "Team", "AssembleOnly", 1))
Global $sfRenderOff = Int(IniRead($sfTeam, "Member" & ($sfIndex + 1), "DisableRendering", 0))
Global $sfInitialized = False, $sfHwnd = 0, $sfGamePID = 0
Global $sfPhase = "Attach", $sfState = "Waiting for character login", $sfPhaseTimer = TimerInit()
Global $sfActionTimer = TimerInit(), $sfHeartbeatTimer = TimerInit(), $sfStartTimer = TimerInit()
Global $sfCycle = 0, $sfRuns = 0, $sfFails = 0, $sfCapturedCount = 0, $sfTotalRunMS = 0
Global $sfRunTimer = 0, $sfBefore = 0, $sfTarget = 0, $sfStep = 0, $sfCastTimer = TimerInit(), $sfCastWait = 0
Global $sfCaptureTimer = TimerInit(), $sfWaypoint = 0, $sfReturnSent = False, $sfMode = "run"
Global $sfUnavailableTimer = 0, $sfLaunchAttempted = False, $sfLaunchedPID = 0
Global $sfBuildLoaded = False, $sfBuildTimer = TimerInit(), $sfAttachLast = 0
Global $sfExpectedSkills[8] = [1948, 1043, 294, 952, 2358, 2353, 1041, 2136]
Global $sfSkillSequence[8] = [1, 2, 4, 7, 3, 5, 6, 8]
Global $sfWaypoints[3][2] = [[-4667, 17917], [-4279, 18221], [-4100, 19829]]

; Prevent two workers attaching to the same configured character, even across sessions.
Global $sfLock = _Singleton("SkelefarmCharacter_" & StringLower(StringReplace($sfCharacter, " ", "_")), 1)
If $sfLock = 0 Then Exit 4
OnAutoItExitRegister("SF_Cleanup")
Log_SetCallback("SF_APILog")
SF_Log("Starting " & $sfCharacter & "; leader=" & $sfLeader)
SF_WriteStatus()
While True
    Sleep(100)
    $sfMode = IniRead($sfCommand, "Control", "Mode", "pause")
    If $sfMode = "stop" Then ExitLoop
    If $sfInitialized And Not ProcessExists($sfGamePID) Then
        SF_Error("Guild Wars client exited; relaunch the team")
        ExitLoop
    EndIf
    If TimerDiff($sfHeartbeatTimer) >= 1000 Then
        If $sfInitialized And Core_IsIngame() Then
            If StringCompare(Player_GetCharName(), $sfCharacter) <> 0 Then SF_Error("Character changed; stop and relaunch the team")
        EndIf
        SF_WriteStatus()
        $sfHeartbeatTimer = TimerInit()
    EndIf
    If $sfPhase = "Error" Then ContinueLoop
    If Not $sfInitialized Then
        SF_Attach()
        ContinueLoop
    EndIf
    ; No commands while loading or on a disconnected / character selection screen.
    If Not Core_IsIngame() Or Map_GetInstanceInfo("IsLoading") Or Agent_GetAgentPtr(-2) = 0 Then
        If $sfUnavailableTimer = 0 Then $sfUnavailableTimer = TimerInit()
        If TimerDiff($sfUnavailableTimer) > 60000 Then SF_Error("Disconnected or map load timed out; relaunch team")
        ContinueLoop
    EndIf
    $sfUnavailableTimer = 0
    If $sfMode = "pause" And Map_GetInstanceInfo("IsOutpost") Then
        If $sfPhase <> "Paused" Then SF_SetPhase("Paused", "Paused in outpost")
        $sfActionTimer = TimerInit()
        ContinueLoop
    ElseIf $sfPhase = "Paused" And $sfMode = "run" Then
        SF_SetPhase("Travel", "Resuming team assembly")
    EndIf
    Switch $sfPhase
        Case "Travel"
            SF_Travel()
        Case "Prepare"
            SF_Prepare()
        Case "Party", "Ready"
            SF_Party()
        Case "Move"
            SF_Move()
        Case "Entry"
            SF_Entry()
        Case "Fight"
            SF_Fight()
        Case "Done"
            SF_Done()
        Case "Return"
            SF_Return()
    EndSwitch
WEnd
Exit

Func SF_SetPhase($phase, $message)
    $sfPhase = $phase
    $sfState = $message
    $sfPhaseTimer = TimerInit()
    $sfActionTimer = TimerInit()
    SF_Log($message)
    SF_WriteStatus()
EndFunc

Func SF_Error($message)
    SF_SetPhase("Error", "Attention: " & $message)
EndFunc

Func SF_Log($message)
    ; FileOpen append and close each line; diagnostic output survives worker exit.
    If FileGetSize($sfLog) > 5242880 Then FileMove($sfLog, $sfLog & ".1", 1)
    Local $h = FileOpen($sfLog, 1 + 128)
    If $h <> -1 Then
        FileWriteLine($h, _NowCalc() & " | " & $sfPhase & " | " & $message)
        FileClose($h)
    EndIf
EndFunc

Func SF_Attach()
    If Not $sfLaunchAttempted Then
        $sfLaunchAttempted = True
        If Int(IniRead($sfTeam, "Member" & ($sfIndex + 1), "LaunchDirect", 0)) Then
            ; Reuse an existing logged-in character instead of launching a duplicate.
            Local $names = "|" & Scanner_GetLoggedCharNames() & "|"
            If Not StringInStr($names, "|" & $sfCharacter & "|") Then
                Local $section = "Member" & ($sfIndex + 1)
                $sfState = "Launching account from local characters.ini"
                SF_WriteStatus()
                _Crypt_Startup()
                $sfLaunchedPID = Launch_LaunchAccountFromINI( _
                    IniRead($sfTeam, $section, "CharactersINI", ""), _
                    IniRead($sfTeam, $section, "Section", $sfCharacter), False, _
                    IniRead($sfTeam, $section, "ExePath", ""), _
                    IniRead($sfTeam, $section, "CryptoSeed", "Encounter_ReBuilt.au3"))
                _Crypt_Shutdown()
                If $sfLaunchedPID = 0 Then
                    SF_Error("Account launch failed; check local credentials, encryption seed and game paths")
                    Return
                EndIf
                ; Login may take time after the playable window is created.
                $sfStartTimer = TimerInit()
                $sfAttachLast = 0
            EndIf
        EndIf
    EndIf
    If TimerDiff($sfStartTimer) > 180000 Then
        SF_Error("Character not found within 180 seconds: " & $sfCharacter)
        Return
    EndIf
    If TimerDiff($sfStartTimer) - $sfAttachLast < 5000 Then Return
    $sfAttachLast = TimerDiff($sfStartTimer)
    If Core_Initialize($sfCharacter, False) = 0 Then Return
    If StringCompare(Player_GetCharName(), $sfCharacter) <> 0 Then
        SF_Error("Attached character does not match configuration")
        Return
    EndIf
    $sfInitialized = True
    $sfHwnd = $g_h_GWWindow
    $sfGamePID = $g_i_GWProcessId
    If $sfRenderOff Then Ui_DisableRendering()
    WinSetState($sfHwnd, "", @SW_MINIMIZE)
    If Not Map_GetInstanceInfo("IsOutpost") Then
        SF_Error("Start in an outpost; no automatic resignation from existing adventures")
        Return
    EndIf
    SF_SetPhase("Travel", "Travelling to Temple of the Ages")
EndFunc

Func SF_LocationMatches()
    Return Map_GetMapID() = $SF_TOA And Map_GetInstanceInfo("IsOutpost") _
        And Map_GetCharacterInfo("Region") = $sfRegion _
        And Map_GetCharacterInfo("Language") = $sfLanguage _
        And Map_GetCharacterInfo("DistrictNumber") = $sfDistrict
EndFunc

Func SF_Travel()
    If SF_LocationMatches() Then
        SF_SetPhase("Prepare", "Checking build and supplies")
        Return
    EndIf
    If TimerDiff($sfPhaseTimer) > 60000 Then
        SF_Error("Cannot reach configured town/district; check travel unlocks and district availability")
        Return
    EndIf
    If TimerDiff($sfActionTimer) < 5000 Then Return
    ; Map_TravelTo ignores a district change if town/region/language already match.
    Map_MoveMap($SF_TOA, $sfRegion, $sfDistrict, $sfLanguage)
    $sfActionTimer = TimerInit()
EndFunc

Func SF_Quantity($model)
    Local $quantity = 0, $item
    For $bag = 1 To 4
        For $slot = 1 To Item_GetBagInfo($bag, "Slots")
            $item = Item_GetItemBySlot($bag, $slot)
            If $item = 0 Then ContinueLoop
            If Item_GetItemInfoByPtr($item, "ModelID") = $model Then $quantity += Item_GetItemInfoByPtr($item, "Quantity")
        Next
    Next
    Return $quantity
EndFunc

Func SF_Mobstopper()
    Local $item
    For $bag = 1 To 4
        For $slot = 1 To Item_GetBagInfo($bag, "Slots")
            $item = Item_GetItemBySlot($bag, $slot)
            If $item = 0 Then ContinueLoop
            If Item_GetItemInfoByPtr($item, "ModelID") = $SF_MOBSTOPPER Then Return $item
        Next
    Next
    Return 0
EndFunc

Func SF_FreeSlots()
    Local $slots = 0
    For $bag = 1 To 4
        $slots += Item_GetBagInfo($bag, "EmptySlots")
    Next
    Return $slots
EndFunc

Func SF_Prepare()
    If Not SF_LocationMatches() Then
        SF_SetPhase("Travel", "Location changed; regrouping")
        Return
    EndIf
    If SF_Mobstopper() = 0 Then
        SF_Error("No Everlasting Mobstopper in carried bags")
        Return
    EndIf
    ; Conservative: reserve an empty slot even if an existing capture stack has room.
    If SF_FreeSlots() < 1 Then
        SF_Error("Inventory full; free a carried bag slot")
        Return
    EndIf
    If Not $sfBuildLoaded Then
        If Not Attribute_LoadSkillTemplate(IniRead($sfTeam, "Team", "Build", "")) Then
            SF_Error("Unable to load the configured skill template")
            Return
        EndIf
        $sfBuildLoaded = True
        $sfBuildTimer = TimerInit()
        Return
    EndIf
    If TimerDiff($sfBuildTimer) < 2500 Then Return
    For $slot = 1 To 8
        If Not Skill_GetSkillbarInfo($slot, "HasSkill") Then
            SF_Error("Build has missing/locked skills; check professions and unlocks")
            Return
        EndIf
        If Skill_GetSkillbarInfo($slot, "SkillID") <> $sfExpectedSkills[$slot - 1] Then
            SF_Error("Skill bar changed during session")
            Return
        EndIf
    Next
    ; Wait for the damage and movement skills before advertising readiness.
    For $slot = 3 To 6
        If Skill_GetSkillbarInfo($slot, "RechargeTime") > 0 Then
            $sfState = "Waiting for skill recharge"
            If TimerDiff($sfPhaseTimer) > 90000 Then SF_Error("Skills did not recharge")
            Return
        EndIf
    Next
    Party_KickAllHeroes()
    Game_SwitchMode(0)
    SF_SetPhase("Party", "Assembling configured team")
EndFunc

Func SF_PeerPath($id)
    Return $sfSession & "\" & $id & ".status.ini"
EndFunc

Func SF_PeerFresh($id)
    Local $path = SF_PeerPath($id)
    Local $stamp = IniRead($path, "Worker", "Stamp", "")
    If $stamp = "" Then Return False
    Local $age = _DateDiff("s", $stamp, _NowCalc())
    If @error Or $age < 0 Or $age > 10 Then Return False
    Local $pid = Int(IniRead($path, "Worker", "PID", 0))
    If Not ProcessExists($pid) Then Return False
    Local $phase = IniRead($path, "Worker", "Phase", "")
    If $phase = "Error" Or $phase = "Stopped" Or $phase = "Paused" Then Return False
    Return True
EndFunc

Func SF_Peer($id, $key, $default = "0")
    Return IniRead(SF_PeerPath($id), "Worker", $key, $default)
EndFunc

Func SF_MyLogin()
    Return Agent_GetAgentInfo(-2, "LoginNumber")
EndFunc

Func SF_IsGameLeader()
    Return SF_MyLogin() > 0 And Party_GetMyPartyPlayerMemberInfo(1, "LoginNumber") = SF_MyLogin()
EndFunc

Func SF_HasLogin($login)
    If $login <= 0 Then Return False
    For $n = 1 To Party_GetMyPartyInfo("ArrayPlayerPartyMemberSize")
        If Party_GetMyPartyPlayerMemberInfo($n, "LoginNumber") = $login And Party_GetMyPartyPlayerMemberInfo($n, "IsConnected") Then Return True
    Next
    Return False
EndFunc

Func SF_ExactParty()
    If Party_GetMyPartyInfo("ArrayPlayerPartyMemberSize") <> $sfCount Then Return False
    If Party_GetMyPartyInfo("ArrayHeroPartyMemberSize") <> 0 Or Party_GetMyPartyInfo("ArrayHenchmanPartyMemberSize") <> 0 Then Return False
    Local $login, $id
    For $n = 0 To $sfCount - 1
        $id = $sfMembers[$n][0]
        If $id = $sfID Then
            $login = SF_MyLogin()
        Else
            If Not SF_PeerFresh($id) Then Return False
            If Int(SF_Peer($id, "Map")) <> $SF_TOA Or Int(SF_Peer($id, "District")) <> $sfDistrict _
                Or Int(SF_Peer($id, "Region")) <> $sfRegion Or Int(SF_Peer($id, "Language")) <> $sfLanguage Then Return False
            If SF_Peer($id, "Mode", "pause") <> "run" Then Return False
            $login = Int(SF_Peer($id, "Login"))
        EndIf
        If Not SF_HasLogin($login) Then Return False
    Next
    If $sfIsLeader Then Return SF_IsGameLeader()
    Return Party_GetMyPartyPlayerMemberInfo(1, "LoginNumber") = Int(SF_Peer($sfLeader, "Login"))
EndFunc

Func SF_AllReady()
    If Not SF_ExactParty() Then Return False
    For $n = 0 To $sfCount - 1
        If $sfMembers[$n][0] = $sfID Then ContinueLoop
        If SF_Peer($sfMembers[$n][0], "Phase", "") <> "Ready" Then Return False
    Next
    Return True
EndFunc

Func SF_Party()
    If Map_GetMapID() = $SF_UW And Map_GetInstanceInfo("IsExplorable") Then
        If $sfIsLeader Then
            SF_Error("Unexpected UW entry before leader approval")
        Else
            SF_StartFight()
        EndIf
        Return
    EndIf
    If Not SF_LocationMatches() Then
        SF_SetPhase("Travel", "Regrouping in configured district")
        Return
    EndIf
    If TimerDiff($sfPhaseTimer) > 180000 And Not SF_ExactParty() Then
        SF_Error("Team assembly timed out; check other workers, team leader, and invites")
        Return
    EndIf
    If SF_ExactParty() Then
        If $sfPhase <> "Ready" Then SF_SetPhase("Ready", "Team ready" )
        If $sfIsLeader And SF_AllReady() Then
            If $sfAssemblyOnly Then
                $sfState = "Assembly verified — assembly-only mode"
                Return
            EndIf
            If Item_GetInventoryInfo("GoldCharacter") < 1000 Then
                If TimerDiff($sfPhaseTimer) > 30000 Then
                    SF_Error("Could not withdraw entry gold; put at least 1,000 gold on leader")
                    Return
                EndIf
                If Item_GetInventoryInfo("GoldStorage") < 1000 Then
                    SF_Error("Leader needs 1,000 gold for entry")
                    Return
                EndIf
                If TimerDiff($sfActionTimer) > 3000 Then
                    Item_WithdrawGold(1000)
                    $sfActionTimer = TimerInit()
                EndIf
                Return
            EndIf
            $sfWaypoint = 0
            ; Pick the closer approach used in the original farm route.
            If Agent_GetDistanceToXY(-3670, 17575) < Agent_GetDistanceToXY(-5150, 17500) Then $sfWaypoint = 1
            SF_SetPhase("Move", "Leader moving to Avatar of Grenth")
        EndIf
        Return
    ElseIf $sfPhase = "Ready" Then
        SF_SetPhase("Party", "Party changed; assembling again")
    EndIf
    If TimerDiff($sfActionTimer) < 3000 Then Return
    $sfActionTimer = TimerInit()
    If $sfIsLeader Then
        If Not SF_IsGameLeader() Then
            Party_LeaveGroup()
            Return
        EndIf
        ; Use live per-district login numbers, never a fixed list of character names.
        For $n = 0 To $sfCount - 1
            Local $id = $sfMembers[$n][0]
            If $id = $sfID Or Not SF_PeerFresh($id) Then ContinueLoop
            If Int(SF_Peer($id, "Map")) <> $SF_TOA Or Int(SF_Peer($id, "District")) <> $sfDistrict _
                Or Int(SF_Peer($id, "Region")) <> $sfRegion Or Int(SF_Peer($id, "Language")) <> $sfLanguage Then ContinueLoop
            Local $login = Int(SF_Peer($id, "Login"))
            If $login > 0 And Not SF_HasLogin($login) Then Party_AddPlayer($login)
        Next
    Else
        If Not SF_PeerFresh($sfLeader) Then Return
        If Int(SF_Peer($sfLeader, "Map")) <> $SF_TOA Or Int(SF_Peer($sfLeader, "District")) <> $sfDistrict _
            Or Int(SF_Peer($sfLeader, "Region")) <> $sfRegion Or Int(SF_Peer($sfLeader, "Language")) <> $sfLanguage Then Return
        Local $leaderParty = Int(SF_Peer($sfLeader, "Party"))
        If $leaderParty <= 0 Then Return
        If Party_GetMyPartyInfo("PartyID") <> $leaderParty Then
            If Party_GetMyPartyInfo("ArrayPlayerPartyMemberSize") > 1 Then
                Party_LeaveGroup()
            Else
                ; Only accept the designated leader's party invitation.
                Party_AcceptInvitation($leaderParty)
            EndIf
        EndIf
    EndIf
EndFunc

Func SF_Move()
    ; Recheck identity/readiness at each step and immediately before paying for entry.
    If Not SF_AllReady() Then
        SF_SetPhase("Party", "A team member is no longer ready")
        Return
    EndIf
    If TimerDiff($sfPhaseTimer) > 45000 Then
        SF_Error("Movement to Grenth timed out")
        Return
    EndIf
    Local $x = $sfWaypoints[$sfWaypoint][0], $y = $sfWaypoints[$sfWaypoint][1]
    If Agent_GetDistanceToXY($x, $y) < 200 Then
        If $sfWaypoint < 2 Then
            $sfWaypoint = 2
        Else
            $sfCycle += 1
            SF_SetPhase("Entry", "Leader requesting UW entry")
        EndIf
        Return
    EndIf
    If TimerDiff($sfActionTimer) > 1000 Then
        Map_Move($x, $y, 0)
        $sfActionTimer = TimerInit()
    EndIf
EndFunc

Func SF_FindModel($model1, $model2 = 0)
    Local $best = 0, $distance = 4000, $model, $d
    ; Exclusive upper bound follows GwAu3's native agent validation.
    For $n = 1 To Agent_GetMaxAgents() - 1
        If Agent_GetAgentPtr($n) = 0 Then ContinueLoop
        If Not Agent_GetAgentInfo($n, "IsLivingType") Then ContinueLoop
        If Agent_GetAgentInfo($n, "IsDead") Then ContinueLoop
        $model = Agent_GetAgentInfo($n, "ModelID")
        If $model <> $model1 And ($model2 = 0 Or $model <> $model2) Then ContinueLoop
        $d = Agent_GetDistance($n)
        If $d < $distance Then
            $distance = $d
            $best = $n
        EndIf
    Next
    Return $best
EndFunc

Func SF_Entry()
    If Map_GetMapID() = $SF_UW And Map_GetInstanceInfo("IsExplorable") Then
        SF_StartFight()
        Return
    EndIf
    If TimerDiff($sfPhaseTimer) > 45000 Then
        SF_Error("UW entry timed out; check Grenth, favor/access, gold, and event availability")
        Return
    EndIf
    If Not SF_AllReady() Then
        SF_SetPhase("Party", "Entry cancelled; team readiness changed")
        Return
    EndIf
    If TimerDiff($sfActionTimer) < 2000 Then Return
    $sfActionTimer = TimerInit()
    Local $npc = SF_FindModel($sfGrenth)
    If $npc = 0 Then
        Chat_SendChat("kneel", "/")
        Return
    EndIf
    Agent_GoNPC($npc)
    ; The original Grenth entry dialogue IDs, paced for server interaction.
    Sleep(350)
    Game_Dialog(0x85)
    Sleep(350)
    Game_Dialog(0x86)
EndFunc

Func SF_StartFight()
    If Not $sfIsLeader Then $sfCycle = Int(SF_Peer($sfLeader, "Cycle"))
    $sfRunTimer = TimerInit()
    $sfBefore = SF_Quantity($SF_CAPTURED)
    $sfTarget = 0
    $sfStep = 0
    $sfCastWait = 0
    $sfCastTimer = TimerInit()
    $sfCaptureTimer = TimerInit()
    SF_SetPhase("Fight", "Finding Skeleton of Dhuum")
EndFunc

Func SF_Finish($success, $reason)
    $sfRuns += 1
    If Not $success Then $sfFails += 1
    $sfTotalRunMS += TimerDiff($sfRunTimer)
    If $success Then $sfCapturedCount += SF_Quantity($SF_CAPTURED) - $sfBefore
    SF_SetPhase("Done", $reason)
EndFunc

Func SF_Fight()
    If Map_GetMapID() <> $SF_UW Then
        SF_Finish(False, "Unexpected map change during farm")
        Return
    EndIf
    If SF_Quantity($SF_CAPTURED) > $sfBefore Then
        Agent_CancelAction()
        SF_Finish(True, "Capture verified in inventory")
        Return
    EndIf
    If Agent_GetAgentInfo(-2, "IsDead") Then
        SF_Finish(False, "Character died before capture")
        Return
    EndIf
    If TimerDiff($sfPhaseTimer) > 30000 Then
        SF_Finish(False, "Capture timed out")
        Return
    EndIf
    If $sfTarget = 0 Then
        $sfTarget = SF_FindModel($sfSkeleton1, $sfSkeleton2)
        If $sfTarget = 0 Then Return
        Agent_ChangeTarget($sfTarget)
        SF_Log("Target agent=" & $sfTarget & ", model=" & Agent_GetAgentInfo($sfTarget, "ModelID"))
    EndIf
    If Agent_GetAgentPtr($sfTarget) = 0 Or Agent_GetAgentInfo($sfTarget, "IsDead") Then
        ; Allow inventory update to arrive before recording a failed capture.
        If TimerDiff($sfPhaseTimer) > 20000 Then SF_Finish(False, "Target lost without a verified capture")
        Return
    EndIf
    If Agent_GetAgentInfo($sfTarget, "HP") < 0.25 Then
        If TimerDiff($sfCaptureTimer) > 1000 Then
            Local $mob = SF_Mobstopper()
            If $mob = 0 Then
                SF_Finish(False, "Mobstopper missing")
                Return
            EndIf
            Agent_ChangeTarget($sfTarget)
            Item_UseItem($mob)
            $sfCaptureTimer = TimerInit()
            $sfState = "Capturing — waiting for inventory confirmation"
        EndIf
        Return
    EndIf
    If TimerDiff($sfCastTimer) < $sfCastWait Or Agent_GetAgentInfo(-2, "IsCasting") Then Return
    If $sfStep >= 8 Then Return
    Local $slot = $sfSkillSequence[$sfStep]
    ; Finish Him is only useful below half health, just as in the original script.
    If $slot = 6 And Agent_GetAgentInfo($sfTarget, "HP") >= 0.49 Then
        $sfStep += 1
        Return
    EndIf
    If Skill_GetSkillbarInfo($slot, "RechargeTime") > 0 Then
        $sfStep += 1
        Return
    EndIf
    Local $skill = Skill_GetSkillbarInfo($slot, "SkillID")
    Local $target = -2
    If $slot = 3 Or $slot = 4 Or $slot = 5 Or $slot = 6 Then $target = $sfTarget
    Skill_UseSkill($slot, $target)
    $sfCastWait = _Max(300, (Skill_GetSkillInfo($skill, "Activation") + Skill_GetSkillInfo($skill, "Aftercast")) * 1000 + 150)
    $sfCastTimer = TimerInit()
    $sfStep += 1
EndFunc

Func SF_AllDone()
    For $n = 0 To $sfCount - 1
        Local $id = $sfMembers[$n][0]
        If $id = $sfID Then ContinueLoop
        If Not SF_PeerFresh($id) Then Return False
        If SF_Peer($id, "Phase", "") <> "Done" Then Return False
        If Int(SF_Peer($id, "Cycle")) <> $sfCycle Then Return False
        If Int(SF_Peer($id, "Map")) <> $SF_UW Then Return False
    Next
    Return True
EndFunc

Func SF_Done()
    If Map_GetMapID() = $SF_TOA Then
        SF_SetPhase("Prepare", "Checking supplies for next run")
        Return
    EndIf
    If $sfIsLeader Then
        ; Give every follower a chance to capture before the entire team resigns.
        If Not SF_AllDone() And TimerDiff($sfPhaseTimer) < 45000 Then Return
        SF_SetPhase("Return", "Resigning and returning team")
        $sfReturnSent = False
    ElseIf SF_PeerFresh($sfLeader) And SF_Peer($sfLeader, "Phase", "") = "Return" Then
        SF_SetPhase("Return", "Leader returning team")
        $sfReturnSent = False
    ElseIf TimerDiff($sfPhaseTimer) > 60000 Then
        SF_Error("Leader did not return team; manual return required")
    EndIf
EndFunc

Func SF_Return()
    If Map_GetMapID() = $SF_TOA And Map_GetInstanceInfo("IsOutpost") Then
        SF_SetPhase("Prepare", "Checking supplies for next run")
        Return
    EndIf
    If TimerDiff($sfPhaseTimer) > 45000 Then
        SF_Error("Return to outpost timed out; manual return required")
        Return
    EndIf
    If Not $sfReturnSent Then
        Chat_SendChat("resign", "/")
        $sfReturnSent = True
    EndIf
    If $sfIsLeader And TimerDiff($sfPhaseTimer) > 7000 And TimerDiff($sfActionTimer) > 3000 Then
        Map_ReturnToOutpost(False)
        $sfActionTimer = TimerInit()
    EndIf
EndFunc

Func SF_WriteStatus()
    Local $text = "[Worker]" & @CRLF
    $text &= "Stamp=" & _NowCalc() & @CRLF & "PID=" & @AutoItPID & @CRLF
    $text &= "Character=" & $sfCharacter & @CRLF & "Phase=" & $sfPhase & @CRLF & "State=" & $sfState & @CRLF
    $text &= "Mode=" & $sfMode & @CRLF & "Cycle=" & $sfCycle & @CRLF
    $text &= "Runs=" & $sfRuns & @CRLF & "Fails=" & $sfFails & @CRLF & "Captured=" & $sfCapturedCount & @CRLF
    $text &= "Rate=" & Round($sfCapturedCount * 3600000 / _Max(1000, TimerDiff($sfStartTimer)), 1) & @CRLF
    If $sfRuns > 0 Then $text &= "AverageSeconds=" & Round($sfTotalRunMS / $sfRuns / 1000, 1) & @CRLF
    If $sfInitialized Then
        $text &= "GamePID=" & $sfGamePID & @CRLF & "Map=" & Map_GetMapID() & @CRLF
        $text &= "Region=" & Map_GetCharacterInfo("Region") & @CRLF & "Language=" & Map_GetCharacterInfo("Language") & @CRLF
        $text &= "District=" & Map_GetCharacterInfo("DistrictNumber") & @CRLF
        $text &= "Party=" & Party_GetMyPartyInfo("PartyID") & @CRLF & "Login=" & SF_MyLogin() & @CRLF
        $text &= "FreeSlots=" & SF_FreeSlots() & @CRLF
    EndIf
    Local $tmp = $sfStatus & ".tmp"
    Local $h = FileOpen($tmp, 2 + 32) ; UTF-16 LE with BOM, matching Python's reader.
    If $h = -1 Then Return
    FileWrite($h, $text)
    FileClose($h)
    FileMove($tmp, $sfStatus, 1)
EndFunc

Func SF_Cleanup()
    Security_CloseMutex($g_h_GameMutex)
    If $sfInitialized And ProcessExists($sfGamePID) Then
        Ui_EnableRendering()
        WinSetState($sfHwnd, "", @SW_SHOW)
    EndIf
    $sfPhase = "Stopped"
    If StringLeft($sfState, 10) <> "Attention:" Then $sfState = "Stopped"
    SF_Log("Worker exited; game left open")
    SF_WriteStatus()
EndFunc

; GwAu3's optional front-end hooks must exist for Au3Check, even when unused.
Func Out($message)
    SF_Log($message)
EndFunc

Func StartBot()
    ; Core_AutoStart is disabled; attachment is driven by the worker state machine.
    Return False
EndFunc

Func _Exit()
    Exit
EndFunc

Func Extend_Write()
    ; No custom write extension is registered by this worker.
EndFunc

Func Extend_AssemblerWriteDetour()
    ; No custom detour extension is registered by this worker.
EndFunc

Func SF_APILog($message, $type, $author)
    SF_Log($author & ": " & $message)
EndFunc

; Launch module's logging adapter deliberately receives no command line/passwords.
Func AddOns_Out($message)
    SF_Log($message)
EndFunc
