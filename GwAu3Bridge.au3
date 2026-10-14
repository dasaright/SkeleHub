; Thin game API bridge. Farm decisions and timing live in worker.py.
#AutoIt3Wrapper_UseX64=n
#NoTrayIcon
#RequireAdmin
#include "vendor\GwAu3\API\_GwAu3.au3"
#include "launcher\AccountLaunch.au3"
$g_b_AutoUpdate = False
Global $bridgePort = 0, $bridgeToken = "", $bridgeLog = "", $bridgeAttached = False, $bridgeSocket = -1, $bridgeLaunchedPID = 0
For $i = 1 To $CmdLine[0] - 1
    Switch $CmdLine[$i]
        Case "--port"
            $bridgePort = Int($CmdLine[$i + 1])
        Case "--token"
            $bridgeToken = $CmdLine[$i + 1]
        Case "--log"
            $bridgeLog = $CmdLine[$i + 1]
    EndSwitch
Next
If $bridgePort <= 0 Or $bridgeToken = "" Then Exit 1
TCPStartup()
OnAutoItExitRegister("BridgeCleanup")
Local $connectTimer = TimerInit()
While $bridgeSocket = -1 And TimerDiff($connectTimer) < 10000
    $bridgeSocket = TCPConnect("127.0.0.1", $bridgePort)
    Sleep(50)
WEnd
If $bridgeSocket = -1 Then Exit 2
TCPSend($bridgeSocket, StringToBinary($bridgeToken & @LF, 4))
Log_SetCallback("BridgeLog")
Local $buffer = "", $idle = TimerInit()
While True
    Local $data = TCPRecv($bridgeSocket, 65536, 1)
    If @error Then ExitLoop
    If BinaryLen($data) > 0 Then
        $buffer &= BinaryToString($data, 4)
        $idle = TimerInit()
    EndIf
    If StringLen($buffer) > 65536 Or TimerDiff($idle) > 90000 Then ExitLoop
    Local $newline = StringInStr($buffer, @LF)
    If $newline = 0 Then
        Sleep(10)
        ContinueLoop
    EndIf
    Local $line = StringLeft($buffer, $newline - 1)
    $buffer = StringTrimLeft($buffer, $newline)
    Local $args = StringSplit($line, @TAB, 1)
    If $args[0] < 1 Then ContinueLoop
    For $n = 2 To $args[0]
        $args[$n] = BridgeDecode($args[$n])
    Next
    Local $reply = BridgeDispatch($args)
    If TCPSend($bridgeSocket, StringToBinary("OK" & @TAB & $reply & @LF, 4)) = 0 Then ExitLoop
    If $args[1] = "close" Then ExitLoop
WEnd
Exit

Func BridgeDispatch(ByRef $a)
    Switch $a[1]
        Case "attach_pid"
            If $a[0] <> 2 Then Return "0"
            $bridgeAttached = Core_Initialize(Int($a[2]), False) <> 0
            Return Int($bridgeAttached)
        Case "attach"
            If $a[0] <> 2 Then Return "0"
            $bridgeAttached = Core_Initialize($a[2], False) <> 0
            Return Int($bridgeAttached)
        Case "launch"
            If $a[0] <> 5 Then Return "0"
            _Crypt_Startup()
            Local $pid = Launch_LaunchAccountFromINI($a[2], $a[3], False, $a[4], $a[5])
            _Crypt_Shutdown()
            $bridgeLaunchedPID = $pid
            Return $pid
        Case "close_game"
            Local $ownedPID = $bridgeLaunchedPID
            If $bridgeAttached Then $ownedPID = $g_i_GWProcessId
            If $ownedPID > 0 Then ProcessClose($ownedPID)
            Return "1"
        Case "close"
            Return "1"
    EndSwitch
    If Not $bridgeAttached Then Return "0"
    Switch $a[1]
        Case "login"
            Local $chosen = -1, $chosenName = ""
            If Core_IsCharacterSelection() And PreGame_Ptr() <> 0 Then
                $chosen = Utils_MakeInt32(PreGame_ChosenCharacter())
                If $chosen >= 0 And $chosen < 256 Then $chosenName = StringStripWS(PreGame_CharName($chosen), 3)
            EndIf
            Return "alive=" & Int(ProcessExists($g_i_GWProcessId) <> 0) & @TAB & "ingame=" & Int(Core_IsIngame()) & @TAB & "selection=" & Int(Core_IsCharacterSelection()) & @TAB & "index=" & $chosen & @TAB & "selected=" & $chosenName
        Case "key"
            If $a[0] <> 2 Then Return "0"
            If Not Core_IsCharacterSelection() Then Return "0"
            Switch $a[2]
                Case "N", "RIGHT", "ENTER"
                    ControlSend($g_h_GWWindow, "", "", "{" & $a[2] & "}")
                Case Else
                    Return "0"
            EndSwitch
        Case "snapshot"
            Local $reply = "map=" & Map_GetMapID() & @TAB & "instance=" & Map_GetInstanceInfo("Type")
            $reply &= @TAB & "ingame=" & Int(Core_IsIngame()) & @TAB & "alive=" & Int(ProcessExists($g_i_GWProcessId) <> 0)
            $reply &= @TAB & "character=" & Player_GetCharName()
            $reply &= @TAB & "primary=" & Party_GetPartyProfessionInfo(-2, "Primary") & @TAB & "secondary=" & Party_GetPartyProfessionInfo(-2, "Secondary")
            $reply &= @TAB & "smiting=" & Attribute_GetPartyAttributeInfo(14, 0, "BaseLevel") & @TAB & "shadow=" & Attribute_GetPartyAttributeInfo(31, 0, "BaseLevel")
            $reply &= @TAB & "game_pid=" & $g_i_GWProcessId & @TAB & "login=" & Agent_GetAgentInfo(-2, "LoginNumber")
            $reply &= @TAB & "party=" & Party_GetMyPartyInfo("PartyID") & @TAB & "leader=" & Party_GetMyPartyPlayerMemberInfo(1, "LoginNumber")
            $reply &= @TAB & "heroes=" & Party_GetMyPartyInfo("ArrayHeroPartyMemberSize") & @TAB & "henchmen=" & Party_GetMyPartyInfo("ArrayHenchmanPartyMemberSize")
            $reply &= @TAB & "region=" & Map_GetCharacterInfo("Region") & @TAB & "language=" & Map_GetCharacterInfo("Language")
            $reply &= @TAB & "district=" & Map_GetCharacterInfo("DistrictNumber") & @TAB & "x=" & Agent_GetAgentInfo(-2, "X") & @TAB & "y=" & Agent_GetAgentInfo(-2, "Y")
            $reply &= @TAB & "dead=" & Int(Agent_GetAgentInfo(-2, "IsDead")) & @TAB & "casting=" & Int(Agent_GetAgentInfo(-2, "IsCasting"))
            $reply &= @TAB & "rendering=" & Int(Ui_GetRenderDisabled()) & @TAB & "roster="
            For $n = 1 To Party_GetMyPartyInfo("ArrayPlayerPartyMemberSize")
                If $n > 1 Then $reply &= ","
                $reply &= Party_GetMyPartyPlayerMemberInfo($n, "LoginNumber") & ":" & Int(Party_GetMyPartyPlayerMemberInfo($n, "IsConnected"))
            Next
            $reply &= @TAB & "skills="
            For $n = 1 To 8
                If $n > 1 Then $reply &= ","
                $reply &= Skill_GetSkillbarInfo($n, "SkillID")
            Next
            $reply &= @TAB & "cooldowns="
            For $n = 1 To 8
                If $n > 1 Then $reply &= ","
                $reply &= Skill_GetSkillbarInfo($n, "RechargeTime")
            Next
            Return $reply
        Case "inventory"
            Local $free = 0
            For $bag = 1 To 4
                $free += Item_GetBagInfo($bag, "EmptySlots")
            Next
            Return "captured=" & BridgeQuantity(32559) & @TAB & "mobstoppers=" & BridgeQuantity(32558) & @TAB & "free=" & $free & @TAB & "gold=" & Item_GetInventoryInfo("GoldCharacter") & @TAB & "storage_gold=" & Item_GetInventoryInfo("GoldStorage")
        Case "travel"
            Map_MoveMap(Int($a[2]), Int($a[3]), Int($a[4]), Int($a[5]))
        Case "build"
            Return Int(Attribute_LoadSkillTemplate($a[2]))
        Case "normal"
            Game_SwitchMode(0)
        Case "kickheroes"
            Party_KickAllHeroes()
        Case "leave"
            Party_LeaveGroup()
        Case "invite"
            Party_AddPlayer(Int($a[2]))
        Case "accept"
            Party_AcceptInvitation(Int($a[2]))
        Case "move"
            Map_Move(Number($a[2]), Number($a[3]), 0)
        Case "nearest"
            Return BridgeNearest(Int($a[2]), Int($a[3]))
        Case "agent"
            Local $id = Int($a[2])
            If Agent_GetAgentPtr($id) = 0 Then Return "exists=0"
            Return "exists=1" & @TAB & "dead=" & Int(Agent_GetAgentInfo($id, "IsDead")) & @TAB & "hp=" & Agent_GetAgentInfo($id, "HP") & @TAB & "model=" & Agent_GetAgentInfo($id, "ModelID") & @TAB & "distance=" & Agent_GetDistance($id)
        Case "target"
            Agent_ChangeTarget(Int($a[2]))
        Case "attack"
            Agent_Attack(Int($a[2]))
        Case "cancel"
            Agent_CancelAction()
        Case "cast"
            Local $slot = Int($a[2]), $skill = Skill_GetSkillbarInfo($slot, "SkillID")
            Skill_UseSkill($slot, Int($a[3]))
            Return _Max(0.3, Skill_GetSkillInfo($skill, "Activation") + Skill_GetSkillInfo($skill, "Aftercast") + 0.15)
        Case "kneel"
            Chat_SendChat("kneel", "/")
        Case "npc"
            Agent_GoNPC(Int($a[2]))
        Case "dialog"
            Game_Dialog(Int($a[2]))
        Case "capture"
            Local $item = BridgeItem(32558)
            If $item = 0 Then Return "0"
            Agent_ChangeTarget(Int($a[2]))
            Item_UseItem($item)
        Case "gold"
            Item_WithdrawGold(1000)
        Case "resign"
            Chat_SendChat("resign", "/")
        Case "return"
            Map_ReturnToOutpost(False)
        Case "render"
            Local $desired = Int($a[2]) <> 0
            If ($desired And Not Ui_GetRenderDisabled()) Or (Not $desired And Ui_GetRenderDisabled()) Then Ui_ToggleRendering()
        Case Else
            Return "0"
    EndSwitch
    Return "1"
EndFunc

Func BridgeNearest($model1, $model2)
    Local $best = 0, $distance = 4000
    For $id = 1 To Agent_GetMaxAgents() - 1
        If Agent_GetAgentPtr($id) = 0 Then ContinueLoop
        If Not Agent_GetAgentInfo($id, "IsLivingType") Or Agent_GetAgentInfo($id, "IsDead") Then ContinueLoop
        Local $model = Agent_GetAgentInfo($id, "ModelID")
        If $model <> $model1 And ($model2 = 0 Or $model <> $model2) Then ContinueLoop
        Local $d = Agent_GetDistance($id)
        If $d < $distance Then
            $best = $id
            $distance = $d
        EndIf
    Next
    Return $best
EndFunc

Func BridgeItem($model)
    For $bag = 1 To 4
        For $slot = 1 To Item_GetBagInfo($bag, "Slots")
            Local $item = Item_GetItemBySlot($bag, $slot)
            If $item <> 0 Then
                If Item_GetItemInfoByPtr($item, "ModelID") = $model Then Return $item
            EndIf
        Next
    Next
    Return 0
EndFunc

Func BridgeQuantity($model)
    Local $total = 0
    For $bag = 1 To 4
        For $slot = 1 To Item_GetBagInfo($bag, "Slots")
            Local $item = Item_GetItemBySlot($bag, $slot)
            If $item <> 0 Then
                If Item_GetItemInfoByPtr($item, "ModelID") = $model Then $total += Item_GetItemInfoByPtr($item, "Quantity")
            EndIf
        Next
    Next
    Return $total
EndFunc

Func BridgeCleanup()
    If $bridgeAttached And ProcessExists($g_i_GWProcessId) Then
        Ui_EnableRendering()
        WinSetState($g_h_GWWindow, "", @SW_SHOW)
    EndIf
    Security_CloseMutex($g_h_GameMutex)
    If $bridgeSocket <> -1 Then TCPCloseSocket($bridgeSocket)
    TCPShutdown()
EndFunc
Func BridgeLog($message, $type = 0, $author = "API")
    If $bridgeLog = "" Then Return
    If FileGetSize($bridgeLog) > 5242880 Then FileMove($bridgeLog, $bridgeLog & ".1", 1)
    Local $h = FileOpen($bridgeLog, 1 + 128)
    If $h <> -1 Then
        FileWriteLine($h, _NowCalc() & " | " & $author & " | " & $message)
        FileClose($h)
    EndIf
EndFunc
Func AddOns_Out($message)
    BridgeLog($message)
EndFunc
Func Out($message)
    BridgeLog($message)
EndFunc
Func StartBot()
    Return False
EndFunc
Func _Exit()
    Exit
EndFunc
Func Extend_Write()
EndFunc
Func Extend_AssemblerWriteDetour()
EndFunc

; Requests are ASCII URL-encoded so TCP fragmentation cannot split UTF-8 path characters.
Func BridgeDecode($text)
    Local $hex = "0x", $i = 1
    While $i <= StringLen($text)
        If StringMid($text, $i, 1) = "%" And $i + 2 <= StringLen($text) Then
            $hex &= StringMid($text, $i + 1, 2)
            $i += 3
        Else
            $hex &= Hex(Asc(StringMid($text, $i, 1)), 2)
            $i += 1
        EndIf
    WEnd
    Return BinaryToString(Binary($hex), 4)
EndFunc
