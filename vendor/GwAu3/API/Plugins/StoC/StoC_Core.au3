#include-once

; Server-to-client event bus. MsgConnDispatch (Net\Msg\MsgConn.cpp) decodes every received message,
; then calls one handler per message id. A detour right before that call copies the subscribed
; messages into a ring buffer, which the script drains with StoC_Poll. Nothing is posted to AutoIt.
;
; Site, with esi = connection, id at conn+0x840 and fields from conn+0x844:
;   8B 46 18          mov eax,[esi+18]      <- detour, stolen
;   FF 75 0C          push [ebp+0C]         <- stolen
;   8B 48 08          mov ecx,[eax+8]       descriptor->dispatch
;   8D 86 40080000    lea eax,[esi+840]
;   50 FF D1          push eax / call ecx
;
; Only the game server channel is kept: conn+8 is the channel, protocol at +0x10 and instance at
; +0x14, both 0. Message ids come from the binary and must be re-checked after each patch.

Global Const $GC_S_STOC_SITE = "8B4618FF750C"
Global Const $GC_I_STOC_STOLEN = 0x6

; The ASM hardcodes these four values: change them together with Assembler_CreateStoC.
Global Const $GC_I_STOC_IDS = 0x400
Global Const $GC_I_STOC_RING = 64
Global Const $GC_I_STOC_FIELDS = 5
Global Const $GC_I_STOC_HEADER_SIZE = 0x10

; Ring header: write count (client), read count (script), overflow count (client).
Global Const $GC_I_STOC_READ_OFFSET = 0x4
Global Const $GC_I_STOC_OVERFLOW_OFFSET = 0x8
Global Const $GC_I_STOC_ENTRY_SIZE = 4 + 4 * $GC_I_STOC_FIELDS

; Message ids used by the helpers below, build 2026-09-01.
Global Const $GC_I_STOC_AGENT_STATUS = 0x0F1   ; (agent, status)
Global Const $GC_I_STOC_EFFECT_REMOVED = 0x044 ; (agent, effect instance id)
Global Const $GC_I_STOC_STATUS_DEAD = 0x10

Global $g_ai_StoCSubscribers[$GC_I_STOC_IDS]
Global $g_i_StoCReadCount = 0

;~ Description: Register the hook site.
Func StoC_AddPattern()
	Scanner_AddPattern("StoC", "8B4618FF750C8B48088D864008000050FFD1", 0x1, "Hook")
EndFunc   ;==>StoC_AddPattern

;~ Description: Resolve the hook site and its return address.
Func StoC_Scanner()
	Local Const $l_p_Start = Scanner_GetScanResult("StoC", $g_ap_ScanResults, "Hook")

	Memory_SetValue("StoCStart", Ptr($l_p_Start))
	Memory_SetValue("StoCReturn", Ptr($l_p_Start + $GC_I_STOC_STOLEN))

	Log_Debug("StoCStart: " & Memory_GetValue("StoCStart"), "Initialize", $g_h_EditText)
EndFunc   ;==>StoC_Scanner

;~ Description: Start reading from wherever the ring already is, re-attach included.
Func StoC_InitializeResult()
	Local Const $l_p_Ring = Memory_GetValue("StoCRing")

	$g_i_StoCReadCount = Memory_Read($l_p_Ring, "dword")
	Memory_Write($l_p_Ring + $GC_I_STOC_READ_OFFSET, $g_i_StoCReadCount)
EndFunc   ;==>StoC_InitializeResult

;~ Description: Reserve the subscription table and the ring.
Func Assembler_CreateStoCData()
	_("StoCFilter/" & $GC_I_STOC_IDS)
	_("StoCRing/" & ($GC_I_STOC_HEADER_SIZE + $GC_I_STOC_RING * $GC_I_STOC_ENTRY_SIZE))
EndFunc   ;==>Assembler_CreateStoCData

;~ Description: Detour proc placed right before the handler call in MsgConnDispatch.
; A full ring counts an overflow and drops the message: the game is never made to wait.
Func Assembler_CreateStoC()
	_("StoCProc:")
	_("pushfd")
	_("pushad")

	; Game server channel only: protocol 0, instance 0.
	_("mov ecx,dword[esi+8] -> 8B 4E 08")
	_("test ecx,ecx -> 85 C9")
	_("jz StoCDone")
	_("cmp dword[ecx+10],0 -> 83 79 10 00")
	_("jnz StoCDone")
	_("cmp dword[ecx+14],0 -> 83 79 14 00")
	_("jnz StoCDone")

	; Subscribed id only.
	_("mov eax,dword[esi+840] -> 8B 86 40 08 00 00")
	_("cmp eax,400 -> 3D 00 04 00 00")
	_("jae StoCDone")
	_("mov ebx,StoCFilter")
	_("cmp byte[ebx+eax],0 -> 80 3C 03 00")
	_("jz StoCDone")

	; Room left: write count - read count < 64.
	_("mov ebx,StoCRing")
	_("mov edx,dword[ebx] -> 8B 13")
	_("mov edi,edx -> 89 D7")
	_("sub edi,dword[ebx+4] -> 2B 7B 04")
	_("cmp edi,40 -> 83 FF 40")
	_("jae StoCFull")

	; Entry = ring + 0x10 + (write count & 63) * 24: the id, then five fields.
	_("and edx,3F -> 83 E2 3F")
	_("imul edx,edx,18 -> 6B D2 18")
	_("lea edi,[ebx+edx+10] -> 8D 7C 13 10")
	_("mov dword[edi],eax -> 89 07")
	_("add edi,4 -> 83 C7 04")
	_("lea esi,[esi+844] -> 8D B6 44 08 00 00")
	_("mov ecx,5 -> B9 05 00 00 00")
	_("cld -> FC")
	_("rep movsd -> F3 A5")

	; Published last, so the script never reads an entry that is still being written.
	_("inc dword[ebx] -> FF 03")
	_("jmp StoCDone")

	_("StoCFull:")
	_("inc dword[ebx+8] -> FF 43 08")

	_("StoCDone:")
	_("popad")
	_("popfd")

	; Stolen instructions, replayed before handing control back.
	_("mov eax,dword[esi+18] -> 8B 46 18")
	_("push dword[ebp+C] -> FF 75 0C")
	_("ljmp StoCReturn")
EndFunc   ;==>Assembler_CreateStoC

;~ Description: Write the detour after reading the six stolen bytes back. Refuses a foreign detour.
Func StoC_Arm()
	Local Const $l_p_Start = Memory_GetValue("StoCStart")
	If $l_p_Start = -1 Or $l_p_Start = 0 Then Return SetError(1, 0, False)

	If StoC_IsHooked($l_p_Start) Then Return SetError(0, 0, True)

	Local Const $l_s_Found = Hex(Memory_Read($l_p_Start, "byte[6]"))
	If $l_s_Found <> $GC_S_STOC_SITE Then
		Log_Error("Unexpected bytes at " & Ptr($l_p_Start) & ": read " & $l_s_Found & _
			", expected " & $GC_S_STOC_SITE, "StoC_Arm", $g_h_EditText)
		Return SetError(2, 0, False)
	EndIf

	Memory_WriteDetour("StoCStart", "StoCProc")
	Return SetError(0, 0, True)
EndFunc   ;==>StoC_Arm

;~ Description: Tell whether the site already carries our own detour.
Func StoC_IsHooked($a_p_Start)
	If Hex(Memory_Read($a_p_Start, "byte"), 2) <> "E9" Then Return False

	Local Const $l_i_Rel = Memory_Read($a_p_Start + 1, "int")
	Return ($a_p_Start + 5 + $l_i_Rel) = Memory_GetValue("StoCProc")
EndFunc   ;==>StoC_IsHooked

;~ Description: Start receiving a message id. Subscriptions are counted, helpers can share one.
Func StoC_Subscribe($a_i_MessageID)
	If $a_i_MessageID < 0 Or $a_i_MessageID >= $GC_I_STOC_IDS Then Return SetError(1, 0, False)
	If Not StoC_Arm() Then Return SetError(2, 0, False)

	$g_ai_StoCSubscribers[$a_i_MessageID] += 1
	If $g_ai_StoCSubscribers[$a_i_MessageID] = 1 Then _
		Memory_Write(Memory_GetValue("StoCFilter") + $a_i_MessageID, 1, "byte")
	Return SetError(0, 0, True)
EndFunc   ;==>StoC_Subscribe

;~ Description: Stop receiving a message id once its last subscriber is gone.
Func StoC_Unsubscribe($a_i_MessageID)
	If $a_i_MessageID < 0 Or $a_i_MessageID >= $GC_I_STOC_IDS Then Return SetError(1, 0, False)
	If $g_ai_StoCSubscribers[$a_i_MessageID] <= 0 Then Return SetError(0, 0, True)

	$g_ai_StoCSubscribers[$a_i_MessageID] -= 1
	If $g_ai_StoCSubscribers[$a_i_MessageID] = 0 Then _
		Memory_Write(Memory_GetValue("StoCFilter") + $a_i_MessageID, 0, "byte")
	Return SetError(0, 0, True)
EndFunc   ;==>StoC_Unsubscribe

;~ Description: Drain the ring into [n][6] rows (id, then five fields), in arrival order.
; Fields beyond a message's own field count hold leftovers of an earlier message: ignore them.
Func StoC_Poll()
	Local $l_av_Events[0][1 + $GC_I_STOC_FIELDS]
	Local Const $l_p_Ring = Memory_GetValue("StoCRing")
	If $l_p_Ring = -1 Or $l_p_Ring = 0 Then Return SetError(1, 0, $l_av_Events)

	Local Const $l_i_Write = Memory_Read($l_p_Ring, "dword")
	Local $l_i_Count = $l_i_Write - $g_i_StoCReadCount
	If $l_i_Count < 0 Then $l_i_Count += 0x100000000
	If $l_i_Count = 0 Then Return SetError(0, 0, $l_av_Events)
	If $l_i_Count > $GC_I_STOC_RING Then Return SetError(2, $l_i_Count, $l_av_Events)

	Local Const $l_i_Dwords = $GC_I_STOC_RING * (1 + $GC_I_STOC_FIELDS)
	Local $l_d_Entries = DllStructCreate("dword[" & $l_i_Dwords & "]")
	Local Const $l_av_Call = DllCall($g_h_Kernel32, "bool", "ReadProcessMemory", _
		"handle", $g_h_GWProcess, _
		"ptr", $l_p_Ring + $GC_I_STOC_HEADER_SIZE, _
		"ptr", DllStructGetPtr($l_d_Entries), _
		"ulong_ptr", DllStructGetSize($l_d_Entries), _
		"ulong_ptr*", 0)
	If @error Or Not IsArray($l_av_Call) Or Not $l_av_Call[0] Then _
		Return SetError(3, 0, $l_av_Events)

	ReDim $l_av_Events[$l_i_Count][1 + $GC_I_STOC_FIELDS]
	Local $l_i_Slot
	For $l_i_Idx = 0 To $l_i_Count - 1
		$l_i_Slot = Mod($g_i_StoCReadCount + $l_i_Idx, $GC_I_STOC_RING)
		For $l_i_Field = 0 To $GC_I_STOC_FIELDS
			$l_av_Events[$l_i_Idx][$l_i_Field] = DllStructGetData($l_d_Entries, 1, _
				$l_i_Slot * (1 + $GC_I_STOC_FIELDS) + $l_i_Field + 1)
		Next
	Next

	$g_i_StoCReadCount = $l_i_Write
	Memory_Write($l_p_Ring + $GC_I_STOC_READ_OFFSET, $g_i_StoCReadCount)
	Return SetError(0, 0, $l_av_Events)
EndFunc   ;==>StoC_Poll

;~ Description: Number of messages dropped because the ring was full, since the client started.
Func StoC_GetOverflow()
	Return Memory_Read(Memory_GetValue("StoCRing") + $GC_I_STOC_OVERFLOW_OFFSET, "dword")
EndFunc   ;==>StoC_GetOverflow

;~ Description: Wait for an agent's rez. True on rez or if already alive, False on timeout.
; Subscribing BEFORE reading the state closes the race: a rez landing in between stays queued.
; Returns on the server message: IsDead follows about one frame later (46 ms measured in game).
Func StoC_WaitRez($a_i_AgentID, $a_i_Timeout = 60000, $a_i_PollMs = 20)
	Local Const $l_i_Agent = Agent_ConvertID($a_i_AgentID)
	If Not StoC_Subscribe($GC_I_STOC_AGENT_STATUS) Then Return SetError(1, 0, False)
	StoC_Poll()

	Local $l_b_Result = Not Agent_GetAgentInfo($l_i_Agent, "IsDead")
	Local $l_av_Events
	Local Const $l_h_Timer = TimerInit()
	While Not $l_b_Result And TimerDiff($l_h_Timer) < $a_i_Timeout
		Sleep($a_i_PollMs)
		$l_av_Events = StoC_Poll()
		For $l_i_Idx = 0 To UBound($l_av_Events) - 1
			If $l_av_Events[$l_i_Idx][0] <> $GC_I_STOC_AGENT_STATUS Then ContinueLoop
			If $l_av_Events[$l_i_Idx][1] <> $l_i_Agent Then ContinueLoop
			If BitAND($l_av_Events[$l_i_Idx][2], $GC_I_STOC_STATUS_DEAD) = 0 Then $l_b_Result = True
		Next
	WEnd

	StoC_Unsubscribe($GC_I_STOC_AGENT_STATUS)
	Return SetError($l_b_Result ? 0 : 2, 0, $l_b_Result)
EndFunc   ;==>StoC_WaitRez

;~ Description: Wait for an effect to end. True when removed or absent, False on timeout.
; The removal message names the effect instance, not the skill: its id is read from the effect
; list first, after subscribing, for the same reason as in StoC_WaitRez.
Func StoC_WaitEffectEnd($a_i_AgentID, $a_i_SkillID, $a_i_Timeout = 60000, $a_i_PollMs = 20)
	Local Const $l_i_Agent = Agent_ConvertID($a_i_AgentID)
	If Not StoC_Subscribe($GC_I_STOC_EFFECT_REMOVED) Then Return SetError(1, 0, False)
	StoC_Poll()

	Local $l_b_Result = Not Agent_GetAgentEffectInfo($a_i_AgentID, $a_i_SkillID, "HasEffect")
	Local $l_i_EffectID = 0
	If Not $l_b_Result Then _
		$l_i_EffectID = Agent_GetAgentEffectInfo($a_i_AgentID, $a_i_SkillID, "EffectID")
	Local $l_av_Events
	Local Const $l_h_Timer = TimerInit()
	While Not $l_b_Result And TimerDiff($l_h_Timer) < $a_i_Timeout
		Sleep($a_i_PollMs)
		$l_av_Events = StoC_Poll()
		For $l_i_Idx = 0 To UBound($l_av_Events) - 1
			If $l_av_Events[$l_i_Idx][0] <> $GC_I_STOC_EFFECT_REMOVED Then ContinueLoop
			If $l_av_Events[$l_i_Idx][1] <> $l_i_Agent Then ContinueLoop
			If $l_av_Events[$l_i_Idx][2] = $l_i_EffectID Then $l_b_Result = True
		Next
	WEnd

	StoC_Unsubscribe($GC_I_STOC_EFFECT_REMOVED)
	Return SetError($l_b_Result ? 0 : 2, 0, $l_b_Result)
EndFunc   ;==>StoC_WaitEffectEnd
