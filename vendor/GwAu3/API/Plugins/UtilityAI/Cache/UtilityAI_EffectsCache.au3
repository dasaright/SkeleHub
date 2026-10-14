#include-once

; ========== Effect Structure Properties ==========
Global Enum $GC_UAI_EFFECT_SkillID, _
	$GC_UAI_EFFECT_AttributeLevel, _
	$GC_UAI_EFFECT_EffectID, _
	$GC_UAI_EFFECT_CasterID, _
	$GC_UAI_EFFECT_Duration, _
	$GC_UAI_EFFECT_Timestamp, _
	$GC_UAI_EFFECT_TimeElapsed, _
	$GC_UAI_EFFECT_TimeRemaining, _
	$GC_UAI_EFFECT_Scale, _
	$GC_UAI_EFFECT_BonusScale, _
	$GC_UAI_EFFECT_COUNT

; ========== Bond Structure Properties ==========
Global Enum $GC_UAI_BOND_SkillID, _
	$GC_UAI_BOND_Unknown, _
	$GC_UAI_BOND_BONDID, _
	$GC_UAI_BOND_TargetAgentID, _
	$GC_UAI_BOND_COUNT

; ========== Visible Effect Structure Properties ==========
Global Enum $GC_UAI_VISEFFECT_EffectType, _
	$GC_UAI_VISEFFECT_EffectID, _
	$GC_UAI_VISEFFECT_HasEnded, _
	$GC_UAI_VISEFFECT_COUNT

; ========== Global Cache ==========
; Effects cache: $g_amx3_EffectsCache[AgentIndex][EffectIndex][Property]
; Bonds cache: $g_amx3_BondsCache[AgentIndex][BondIndex][Property]
; VisibleEffects cache: $g_amx3_VisEffectsCache[AgentIndex][VisEffectIndex][Property]
Global $g_amx3_EffectsCache[1][32][$GC_UAI_EFFECT_COUNT]
Global $g_amx3_BondsCache[1][32][$GC_UAI_EFFECT_COUNT]
Global $g_amx3_VisEffectsCache[1][32][$GC_UAI_EFFECT_COUNT]

Global $g_ai_EffectsCount[1]
Global $g_ai_BondsCount[1]
Global $g_ai_VisEffectsCount[1]

; ========== Dedicated single-slot player caches ==========
Global $g_amx3_PlayerEffects[1][32][$GC_UAI_EFFECT_COUNT]
Global $g_amx3_PlayerBonds[1][32][$GC_UAI_BOND_COUNT]
Global $g_amx3_PlayerVisEffects[1][32][$GC_UAI_VISEFFECT_COUNT]

Global $g_i_PlayerEffectsCount = 0
Global $g_i_PlayerBondsCount = 0
Global $g_i_PlayerVisEffectsCount = 0

; ========== Dervish-specific flash-enchantment timestamp ==========
Global $g_i_LastFeederEnchTimestamp = 0

; ========== Shared struct templates ==========
Func UAI_GetEffectStruct()
	Static $s_d_EffectStruct = Memory_CreateArrayStructure( _
		"long SkillID[0x0];" & _
		"dword AttributeLevel[0x4];" & _
		"long EffectID[0x8];" & _
		"dword CasterID[0xC];" & _
		"float Duration[0x10];" & _
		"dword Timestamp[0x14]", _
		0x18)
	Return $s_d_EffectStruct
EndFunc

Func UAI_GetBondStruct()
	Static $s_d_BondStruct = Memory_CreateArrayStructure( _
		"long SkillID[0x0];" & _
		"dword Unknown[0x4];" & _
		"long BondID[0x8];" & _
		"dword TargetAgentID[0xC]", _
		0x10)
	Return $s_d_BondStruct
EndFunc

Func UAI_GetVisibleEffectStruct()
	Static $s_d_VisEffectStruct = Memory_CreateStructure( _
		"dword EffectType[0x0];" & _
		"dword EffectID[0x4];" & _
		"dword HasEnded[0x8]")
	Return $s_d_VisEffectStruct
EndFunc

Func UAI_GetAgentEffectStruct()
	Static $s_d_AgentEffectStruct = Memory_CreateArrayStructure( _
		"dword AgentID[0x0];" & _
		"ptr BondArray[0x4];" & _
		"long BondCount[0xC];" & _
		"ptr EffectArray[0x14];" & _
		"long EffectCount[0x1C]", _
		0x24)
	Return $s_d_AgentEffectStruct
EndFunc

; ========== Shared fill helpers (single source of truth for struct -> cache mapping) ==========
Func UAI_FillEffectRows(ByRef $a_amx3_Target, $a_i_Index, $a_amx2_Src, $a_i_Count)
	For $k = 0 To $a_i_Count - 1
		$a_amx3_Target[$a_i_Index][$k][$GC_UAI_EFFECT_SkillID] = $a_amx2_Src[$k][0]
		$a_amx3_Target[$a_i_Index][$k][$GC_UAI_EFFECT_AttributeLevel] = $a_amx2_Src[$k][1]
		$a_amx3_Target[$a_i_Index][$k][$GC_UAI_EFFECT_EffectID] = $a_amx2_Src[$k][2]
		$a_amx3_Target[$a_i_Index][$k][$GC_UAI_EFFECT_CasterID] = $a_amx2_Src[$k][3]
		$a_amx3_Target[$a_i_Index][$k][$GC_UAI_EFFECT_Duration] = $a_amx2_Src[$k][4]
		$a_amx3_Target[$a_i_Index][$k][$GC_UAI_EFFECT_Timestamp] = $a_amx2_Src[$k][5]
	Next
EndFunc

Func UAI_FillBondRows(ByRef $a_amx3_Target, $a_i_Index, $a_amx2_Src, $a_i_Count)
	For $k = 0 To $a_i_Count - 1
		$a_amx3_Target[$a_i_Index][$k][$GC_UAI_BOND_SkillID] = $a_amx2_Src[$k][0]
		$a_amx3_Target[$a_i_Index][$k][$GC_UAI_BOND_Unknown] = $a_amx2_Src[$k][1]
		$a_amx3_Target[$a_i_Index][$k][$GC_UAI_BOND_BONDID] = $a_amx2_Src[$k][2]
		$a_amx3_Target[$a_i_Index][$k][$GC_UAI_BOND_TargetAgentID] = $a_amx2_Src[$k][3]
	Next
EndFunc

Func UAI_FillVisEffectRows(ByRef $a_amx3_Target, $a_i_Index, $a_p_AgentPtr)
	Local $l_d_Struct = UAI_GetVisibleEffectStruct()
	Local $l_p_TList = $a_p_AgentPtr + 0x174
	Local $l_av_Iterator = Utils_TList_CreateIterator($l_p_TList)

	Local $l_i_Count = 0
	Local $l_p_Current = Utils_TList_Iterator_Current($l_av_Iterator)

	While $l_p_Current <> 0 And $l_i_Count < 31
		Local $l_av_Node = Memory_ReadStruct($l_p_Current, $l_d_Struct)
		If @error Then ExitLoop

		$a_amx3_Target[$a_i_Index][$l_i_Count][$GC_UAI_VISEFFECT_EffectType] = $l_av_Node[0]
		$a_amx3_Target[$a_i_Index][$l_i_Count][$GC_UAI_VISEFFECT_EffectID]   = $l_av_Node[1]
		$a_amx3_Target[$a_i_Index][$l_i_Count][$GC_UAI_VISEFFECT_HasEnded]   = $l_av_Node[2]

		$l_i_Count += 1
		If Not Utils_TList_Iterator_Next($l_av_Iterator) Then ExitLoop
		$l_p_Current = Utils_TList_Iterator_Current($l_av_Iterator)
	WEnd
	Return $l_i_Count
EndFunc

; ========== Internal: Cache Effects + Bonds for all cached agents ==========
Func UAI_CacheAgentEffectsAndBonds()
	; Full reset: fresh zero-filled arrays each frame (big caches + player mirrors)
	Global $g_amx3_EffectsCache[1][32][$GC_UAI_EFFECT_COUNT]
	Global $g_amx3_BondsCache[1][32][$GC_UAI_EFFECT_COUNT]
	Global $g_ai_EffectsCount[1]
	Global $g_ai_BondsCount[1]

	Global $g_amx3_PlayerEffects[1][32][$GC_UAI_EFFECT_COUNT]
	Global $g_amx3_PlayerBonds[1][32][$GC_UAI_BOND_COUNT]
	$g_i_PlayerEffectsCount = 0
	$g_i_PlayerBondsCount = 0

	Local $l_i_AgentCount = $g_i_AgentCacheCount
	If $l_i_AgentCount = 0 Then Return SetError(1, 0, False)

	ReDim $g_amx3_EffectsCache[$l_i_AgentCount + 1][32][$GC_UAI_EFFECT_COUNT]
	ReDim $g_ai_EffectsCount[$l_i_AgentCount + 1]
	ReDim $g_amx3_BondsCache[$l_i_AgentCount + 1][32][$GC_UAI_BOND_COUNT]
	ReDim $g_ai_BondsCount[$l_i_AgentCount + 1]

	Local $l_p_AgentEffectsBase = World_GetWorldInfo("AgentEffectsArray")
	Local $l_i_AgentEffectsSize = World_GetWorldInfo("AgentEffectsArraySize")
	If $l_p_AgentEffectsBase = 0 Or $l_i_AgentEffectsSize = 0 Then Return SetError(2, 0, False)

	; Single bulk read of the whole AgentEffects array
	Local $l_amx2_Entries = Memory_ReadArrayStruct($l_p_AgentEffectsBase, $l_i_AgentEffectsSize, UAI_GetAgentEffectStruct())
	If @error Then Return SetError(3, 0, False)

	For $j = 0 To $l_i_AgentEffectsSize - 1
		Local $l_i_AgentID = $l_amx2_Entries[$j][0]
		If $l_i_AgentID = 0 Then ContinueLoop

		Local $l_i_Index = UAI_GetIndexByID($l_i_AgentID)
		If $l_i_Index = 0 Then ContinueLoop ; agent not cached / out of range
		Local $l_b_IsPlayer = ($l_i_Index = $g_i_PlayerCacheIndex)

		; --- effects ---
		Local $l_p_EffectArray = $l_amx2_Entries[$j][3]
		Local $l_i_EffectCount = $l_amx2_Entries[$j][4]
		If $l_p_EffectArray <> 0 And $l_i_EffectCount > 0 Then
			If $l_i_EffectCount > 31 Then $l_i_EffectCount = 31
			Local $l_amx2_AllEffects = Memory_ReadArrayStruct($l_p_EffectArray, $l_i_EffectCount, UAI_GetEffectStruct())
			If Not @error Then
				UAI_FillEffectRows($g_amx3_EffectsCache, $l_i_Index, $l_amx2_AllEffects, $l_i_EffectCount)
				$g_ai_EffectsCount[$l_i_Index] = $l_i_EffectCount
				; mirror into the dedicated player cache (same in-memory source, no extra RPM)
				If $l_b_IsPlayer Then
					UAI_FillEffectRows($g_amx3_PlayerEffects, 0, $l_amx2_AllEffects, $l_i_EffectCount)
					$g_i_PlayerEffectsCount = $l_i_EffectCount
				EndIf
			EndIf
		EndIf

		; --- bonds ---
		Local $l_p_BondArray = $l_amx2_Entries[$j][1]
		Local $l_i_BondCount = $l_amx2_Entries[$j][2]
		If $l_p_BondArray <> 0 And $l_i_BondCount > 0 Then
			If $l_i_BondCount > 31 Then $l_i_BondCount = 31
			Local $l_amx2_AllBonds = Memory_ReadArrayStruct($l_p_BondArray, $l_i_BondCount, UAI_GetBondStruct())
			If Not @error Then
				UAI_FillBondRows($g_amx3_BondsCache, $l_i_Index, $l_amx2_AllBonds, $l_i_BondCount)
				$g_ai_BondsCount[$l_i_Index] = $l_i_BondCount
				If $l_b_IsPlayer Then
					UAI_FillBondRows($g_amx3_PlayerBonds, 0, $l_amx2_AllBonds, $l_i_BondCount)
					$g_i_PlayerBondsCount = $l_i_BondCount
				EndIf
			EndIf
		EndIf
	Next

	Return True
EndFunc

; ========== Internal: Cache Visible Effects for all cached agents ==========
Func UAI_CacheAgentVisibleEffects()
	; Full reset: fresh zero-filled arrays each frame (big cache + player mirror)
	Global $g_amx3_VisEffectsCache[1][32][$GC_UAI_EFFECT_COUNT]
	Global $g_amx3_PlayerVisEffects[1][32][$GC_UAI_VISEFFECT_COUNT]
	Global $g_ai_VisEffectsCount[1]
	$g_i_PlayerVisEffectsCount = 0

	Local $l_i_AgentCount = $g_i_AgentCacheCount
	If $l_i_AgentCount = 0 Then Return SetError(1, 0, False)

	ReDim $g_amx3_VisEffectsCache[$l_i_AgentCount + 1][32][$GC_UAI_VISEFFECT_COUNT]
	ReDim $g_ai_VisEffectsCount[$l_i_AgentCount + 1]

	For $i = 1 To $l_i_AgentCount
		; Only living agents have visible effects
		If $g_amx2_AgentCache[$i][$GC_UAI_AGENT_IsLivingType] = False Then ContinueLoop

		Local $l_p_AgentPtr = $g_amx2_AgentCache[$i][$GC_UAI_AGENT_Ptr]
		Local $l_i_Count = UAI_FillVisEffectRows($g_amx3_VisEffectsCache, $i, $l_p_AgentPtr)
		$g_ai_VisEffectsCount[$i] = $l_i_Count

		; mirror into the dedicated player cache (copy the rows we just read -- avoids re-walking the TList)
		If $i = $g_i_PlayerCacheIndex Then
			For $k = 0 To $l_i_Count - 1
				$g_amx3_PlayerVisEffects[0][$k][$GC_UAI_VISEFFECT_EffectType] = $g_amx3_VisEffectsCache[$i][$k][$GC_UAI_VISEFFECT_EffectType]
				$g_amx3_PlayerVisEffects[0][$k][$GC_UAI_VISEFFECT_EffectID]   = $g_amx3_VisEffectsCache[$i][$k][$GC_UAI_VISEFFECT_EffectID]
				$g_amx3_PlayerVisEffects[0][$k][$GC_UAI_VISEFFECT_HasEnded]   = $g_amx3_VisEffectsCache[$i][$k][$GC_UAI_VISEFFECT_HasEnded]
			Next
			$g_i_PlayerVisEffectsCount = $l_i_Count
		EndIf
	Next

	Return True
EndFunc

; ========== Player-only: refresh effects + bonds (one bulk read of AgentEffects) ==========
Func UAI_CachePlayerEffectsAndBonds()
	Global $g_amx3_PlayerEffects[1][32][$GC_UAI_EFFECT_COUNT]
	Global $g_amx3_PlayerBonds[1][32][$GC_UAI_BOND_COUNT]
	$g_i_PlayerEffectsCount = 0
	$g_i_PlayerBondsCount = 0

	Local $l_i_MyID = UAI_GetPlayerInfo($GC_UAI_AGENT_ID)
	If $l_i_MyID = 0 Then Return SetError(1, 0, False)

	Local $l_p_Base = World_GetWorldInfo("AgentEffectsArray")
	Local $l_i_Size = World_GetWorldInfo("AgentEffectsArraySize")
	If $l_p_Base = 0 Or $l_i_Size = 0 Then Return SetError(2, 0, False)

	Local $l_amx2_Entries = Memory_ReadArrayStruct($l_p_Base, $l_i_Size, UAI_GetAgentEffectStruct())
	If @error Then Return SetError(3, 0, False)

	For $j = 0 To $l_i_Size - 1
		If $l_amx2_Entries[$j][0] <> $l_i_MyID Then ContinueLoop

		; effects
		Local $l_p_EffectArray = $l_amx2_Entries[$j][3]
		Local $l_i_EffectCount = $l_amx2_Entries[$j][4]
		If $l_p_EffectArray <> 0 And $l_i_EffectCount > 0 Then
			If $l_i_EffectCount > 31 Then $l_i_EffectCount = 31
			Local $l_amx2_Eff = Memory_ReadArrayStruct($l_p_EffectArray, $l_i_EffectCount, UAI_GetEffectStruct())
			If Not @error Then
				UAI_FillEffectRows($g_amx3_PlayerEffects, 0, $l_amx2_Eff, $l_i_EffectCount)
				$g_i_PlayerEffectsCount = $l_i_EffectCount
			EndIf
		EndIf

		; bonds
		Local $l_p_BondArray = $l_amx2_Entries[$j][1]
		Local $l_i_BondCount = $l_amx2_Entries[$j][2]
		If $l_p_BondArray <> 0 And $l_i_BondCount > 0 Then
			If $l_i_BondCount > 31 Then $l_i_BondCount = 31
			Local $l_amx2_Bond = Memory_ReadArrayStruct($l_p_BondArray, $l_i_BondCount, UAI_GetBondStruct())
			If Not @error Then
				UAI_FillBondRows($g_amx3_PlayerBonds, 0, $l_amx2_Bond, $l_i_BondCount)
				$g_i_PlayerBondsCount = $l_i_BondCount
			EndIf
		EndIf

		Return True ; player entry found and processed
	Next

	Return True ; player not present in the array -> no effects/bonds (already reset)
EndFunc

; ========== Player-only: refresh visible effects (TList walk off the player ptr) ==========
Func UAI_CachePlayerVisibleEffects()
	Global $g_amx3_PlayerVisEffects[1][32][$GC_UAI_VISEFFECT_COUNT]
	$g_i_PlayerVisEffectsCount = 0

	Local $l_p_PlayerPtr = UAI_GetPlayerInfo($GC_UAI_AGENT_Ptr)
	If $l_p_PlayerPtr = 0 Then Return SetError(1, 0, False)

	$g_i_PlayerVisEffectsCount = UAI_FillVisEffectRows($g_amx3_PlayerVisEffects, 0, $l_p_PlayerPtr)
	Return True
EndFunc

; ========== Public: Check if agent has effect ==========
Func UAI_AgentHasEffect($a_i_AgentID, $a_i_SkillID)
	Local $l_i_Index = UAI_GetIndexByID($a_i_AgentID)
	If $l_i_Index = 0 Then Return False

	Local $l_i_Count = $g_ai_EffectsCount[$l_i_Index]
	For $i = 0 To $l_i_Count - 1
		If $g_amx3_EffectsCache[$l_i_Index][$i][$GC_UAI_EFFECT_SkillID] = $a_i_SkillID Then Return True
	Next

	Return False
EndFunc

; ========== Public: Check if player has effect ==========
Func UAI_PlayerHasEffect($a_i_SkillID)
	For $i = 0 To $g_i_PlayerEffectsCount - 1
		If $g_amx3_PlayerEffects[0][$i][$GC_UAI_EFFECT_SkillID] = $a_i_SkillID Then Return True
	Next
	Return False
EndFunc

; ========== Public: Get effect info ==========
Func UAI_GetAgentEffectInfo($a_i_AgentID, $a_i_SkillID, $a_i_Property)
	If $a_i_Property < 0 Or $a_i_Property >= $GC_UAI_EFFECT_COUNT Then Return 0

	Local $l_i_Index = UAI_GetIndexByID($a_i_AgentID)
	If $l_i_Index = 0 Then Return 0

	Local $l_i_Count = $g_ai_EffectsCount[$l_i_Index]
	For $i = 0 To $l_i_Count - 1
		If $g_amx3_EffectsCache[$l_i_Index][$i][$GC_UAI_EFFECT_SkillID] = $a_i_SkillID Then
			; Handle dynamic properties (calculated, not cached)
			Switch $a_i_Property
				Case $GC_UAI_EFFECT_TimeElapsed
					Local $l_i_Timestamp = $g_amx3_EffectsCache[$l_i_Index][$i][$GC_UAI_EFFECT_Timestamp]
					If $l_i_Timestamp = 0 Then Return 0 ; maintained effect: no start time
					Return BitAND(Skill_GetSkillTimer() - $l_i_Timestamp, 0xFFFFFFFF)
				Case $GC_UAI_EFFECT_TimeRemaining
					Local $l_i_Timestamp = $g_amx3_EffectsCache[$l_i_Index][$i][$GC_UAI_EFFECT_Timestamp]
					If $l_i_Timestamp = 0 Then Return 0x7FFFFFFF ; maintained effect: does not expire
					Local $l_f_Duration = $g_amx3_EffectsCache[$l_i_Index][$i][$GC_UAI_EFFECT_Duration]
					Return $l_f_Duration * 1000 - BitAND(Skill_GetSkillTimer() - $l_i_Timestamp, 0xFFFFFFFF)
				Case $GC_UAI_EFFECT_Scale
					Local $l_i_Scale0 = Skill_GetSkillInfo($a_i_SkillID, "Scale0")
					Local $l_i_Scale15 = Skill_GetSkillInfo($a_i_SkillID, "Scale15")
					Local $l_i_AttrLevel = $g_amx3_EffectsCache[$l_i_Index][$i][$GC_UAI_EFFECT_AttributeLevel]
					Return Floor($l_i_Scale0 + (($l_i_Scale15 - $l_i_Scale0) / 15) * $l_i_AttrLevel)
				Case $GC_UAI_EFFECT_BonusScale
					Local $l_i_BonusScale0 = Skill_GetSkillInfo($a_i_SkillID, "BonusScale0")
					Local $l_i_BonusScale15 = Skill_GetSkillInfo($a_i_SkillID, "BonusScale15")
					Local $l_i_AttrLevel = $g_amx3_EffectsCache[$l_i_Index][$i][$GC_UAI_EFFECT_AttributeLevel]
					Return Floor($l_i_BonusScale0 + (($l_i_BonusScale15 - $l_i_BonusScale0) / 15) * $l_i_AttrLevel)
				Case Else
					Return $g_amx3_EffectsCache[$l_i_Index][$i][$a_i_Property]
			EndSwitch
		EndIf
	Next

	Return 0
EndFunc

; ========== Public: Get player effect info ==========
Func UAI_GetPlayerEffectInfo($a_i_SkillID, $a_i_Property)
	If $a_i_Property < 0 Or $a_i_Property >= $GC_UAI_EFFECT_COUNT Then Return 0

	For $i = 0 To $g_i_PlayerEffectsCount - 1
		If $g_amx3_PlayerEffects[0][$i][$GC_UAI_EFFECT_SkillID] = $a_i_SkillID Then
			; Handle dynamic properties (calculated, not cached)
			Switch $a_i_Property
				Case $GC_UAI_EFFECT_TimeElapsed
					Local $l_i_Timestamp = $g_amx3_PlayerEffects[0][$i][$GC_UAI_EFFECT_Timestamp]
					If $l_i_Timestamp = 0 Then Return 0 ; maintained effect: no start time
					Return BitAND(Skill_GetSkillTimer() - $l_i_Timestamp, 0xFFFFFFFF)
				Case $GC_UAI_EFFECT_TimeRemaining
					Local $l_i_Timestamp = $g_amx3_PlayerEffects[0][$i][$GC_UAI_EFFECT_Timestamp]
					If $l_i_Timestamp = 0 Then Return 0x7FFFFFFF ; maintained effect: does not expire
					Local $l_f_Duration = $g_amx3_PlayerEffects[0][$i][$GC_UAI_EFFECT_Duration]
					Return $l_f_Duration * 1000 - BitAND(Skill_GetSkillTimer() - $l_i_Timestamp, 0xFFFFFFFF)
				Case $GC_UAI_EFFECT_Scale
					Local $l_i_Scale0 = Skill_GetSkillInfo($a_i_SkillID, "Scale0")
					Local $l_i_Scale15 = Skill_GetSkillInfo($a_i_SkillID, "Scale15")
					Local $l_i_AttrLevel = $g_amx3_PlayerEffects[0][$i][$GC_UAI_EFFECT_AttributeLevel]
					Return Floor($l_i_Scale0 + (($l_i_Scale15 - $l_i_Scale0) / 15) * $l_i_AttrLevel)
				Case $GC_UAI_EFFECT_BonusScale
					Local $l_i_BonusScale0 = Skill_GetSkillInfo($a_i_SkillID, "BonusScale0")
					Local $l_i_BonusScale15 = Skill_GetSkillInfo($a_i_SkillID, "BonusScale15")
					Local $l_i_AttrLevel = $g_amx3_PlayerEffects[0][$i][$GC_UAI_EFFECT_AttributeLevel]
					Return Floor($l_i_BonusScale0 + (($l_i_BonusScale15 - $l_i_BonusScale0) / 15) * $l_i_AttrLevel)
				Case Else
					Return $g_amx3_PlayerEffects[0][$i][$a_i_Property]
			EndSwitch
		EndIf
	Next

	Return 0
EndFunc

; ========== Public: Get agent effect count ==========
Func UAI_GetAgentEffectCount($a_i_AgentID)
	Local $l_i_Index = UAI_GetIndexByID($a_i_AgentID)
	If $l_i_Index = 0 Then Return 0
	Return $g_ai_EffectsCount[$l_i_Index]
EndFunc

; ========== Public: Get player effect count ==========
Func UAI_GetPlayerEffectCount()
	Return $g_i_PlayerEffectsCount
EndFunc

; ========== Public: Check if agent upkeeps bonds ==========
Func UAI_AgentUpkeepsBond($a_i_AgentID, $a_i_SkillID)
	Local $l_i_Index = UAI_GetIndexByID($a_i_AgentID)
	If $l_i_Index = 0 Then Return False

	Local $l_i_Count = $g_ai_BondsCount[$l_i_Index]
	For $i = 0 To $l_i_Count - 1
		If $g_amx3_BondsCache[$l_i_Index][$i][$GC_UAI_BOND_SkillID] = $a_i_SkillID Then Return True
	Next

	Return False
EndFunc

; ========== Public: Check if player upkeeps bonds ==========
Func UAI_PlayerUpkeepsBond($a_i_SkillID)
	For $i = 0 To $g_i_PlayerBondsCount - 1
		If $g_amx3_PlayerBonds[0][$i][$GC_UAI_BOND_SkillID] = $a_i_SkillID Then Return True
	Next
	Return False
EndFunc

; ========== Public: Get bond info ==========
Func UAI_GetAgentBondInfo($a_i_AgentID, $a_i_SkillID, $a_i_Property)
	If $a_i_Property < 0 Or $a_i_Property >= $GC_UAI_BOND_COUNT Then Return 0

	Local $l_i_Index = UAI_GetIndexByID($a_i_AgentID)
	If $l_i_Index = 0 Then Return 0

	Local $l_i_Count = $g_ai_BondsCount[$l_i_Index]
	For $i = 0 To $l_i_Count - 1
		If $g_amx3_BondsCache[$l_i_Index][$i][$GC_UAI_BOND_SkillID] = $a_i_SkillID Then
			Return $g_amx3_BondsCache[$l_i_Index][$i][$a_i_Property]
		EndIf
	Next

	Return 0
EndFunc

; ========== Public: Get player bond info ==========
Func UAI_GetPlayerBondInfo($a_i_SkillID, $a_i_Property)
	If $a_i_Property < 0 Or $a_i_Property >= $GC_UAI_BOND_COUNT Then Return 0

	For $i = 0 To $g_i_PlayerBondsCount - 1
		If $g_amx3_PlayerBonds[0][$i][$GC_UAI_BOND_SkillID] = $a_i_SkillID Then
			Return $g_amx3_PlayerBonds[0][$i][$a_i_Property]
		EndIf
	Next

	Return 0
EndFunc

; ========== Public: Get agent bond count ==========
Func UAI_GetAgentBondCount($a_i_AgentID)
	Local $l_i_Index = UAI_GetIndexByID($a_i_AgentID)
	If $l_i_Index = 0 Then Return 0
	Return $g_ai_BondsCount[$l_i_Index]
EndFunc

; ========== Public: Get player bond count ==========
Func UAI_GetPlayerBondCount()
	Return $g_i_PlayerBondsCount
EndFunc

; ========== Public: Check if agent has visible effect ==========
Func UAI_AgentHasVisibleEffect($a_i_AgentID, $a_i_EffectType, $a_i_EffectID)
	Local $l_i_Index = UAI_GetIndexByID($a_i_AgentID)
	If $l_i_Index = 0 Then Return False

	Local $l_i_Count = $g_ai_VisEffectsCount[$l_i_Index]
	For $i = 0 To $l_i_Count - 1
		If $g_amx3_VisEffectsCache[$l_i_Index][$i][$GC_UAI_VISEFFECT_EffectType] <> $a_i_EffectType Then ContinueLoop
		If $g_amx3_VisEffectsCache[$l_i_Index][$i][$GC_UAI_VISEFFECT_EffectID] = $a_i_EffectID Then Return True
	Next

	Return False
EndFunc

; ========== Public: Check if player has visible effect ==========
Func UAI_PlayerHasVisibleEffect($a_i_EffectType, $a_i_EffectID)
	For $i = 0 To $g_i_PlayerVisEffectsCount - 1
		If $g_amx3_PlayerVisEffects[0][$i][$GC_UAI_VISEFFECT_EffectType] <> $a_i_EffectType Then ContinueLoop
		If $g_amx3_PlayerVisEffects[0][$i][$GC_UAI_VISEFFECT_EffectID] = $a_i_EffectID Then Return True
	Next
	Return False
EndFunc

; ========== Public: Get visible effect info ==========
Func UAI_GetAgentVisibleEffectInfo($a_i_AgentID)
	Local $l_ai2_VisEffects[1][1] = [[0]]
	Local $l_i_Index = UAI_GetIndexByID($a_i_AgentID)
	If $l_i_Index = 0 Then Return $l_ai2_VisEffects

	Local $l_i_Count = $g_ai_VisEffectsCount[$l_i_Index]
	ReDim $l_ai2_VisEffects[1 + $l_i_Count][3]
	$l_ai2_VisEffects[0][0] = $l_i_Count

	For $i = 1 To $l_i_Count
		$l_ai2_VisEffects[$i][0] = $g_amx3_VisEffectsCache[$l_i_Index][$i - 1][$GC_UAI_VISEFFECT_EffectType]
		$l_ai2_VisEffects[$i][1] = $g_amx3_VisEffectsCache[$l_i_Index][$i - 1][$GC_UAI_VISEFFECT_EffectID]
		$l_ai2_VisEffects[$i][2] = $g_amx3_VisEffectsCache[$l_i_Index][$i - 1][$GC_UAI_VISEFFECT_HasEnded]
	Next

	Return $l_ai2_VisEffects
EndFunc

; ========== Public: Get player visible effect info ==========
Func UAI_GetPlayerVisibleEffectInfo()
	Local $l_ai2_VisEffects[1][1] = [[0]]
	Local $l_i_Count = $g_i_PlayerVisEffectsCount
	ReDim $l_ai2_VisEffects[1 + $l_i_Count][3]
	$l_ai2_VisEffects[0][0] = $l_i_Count

	For $i = 1 To $l_i_Count
		$l_ai2_VisEffects[$i][0] = $g_amx3_PlayerVisEffects[0][$i - 1][$GC_UAI_VISEFFECT_EffectType]
		$l_ai2_VisEffects[$i][1] = $g_amx3_PlayerVisEffects[0][$i - 1][$GC_UAI_VISEFFECT_EffectID]
		$l_ai2_VisEffects[$i][2] = $g_amx3_PlayerVisEffects[0][$i - 1][$GC_UAI_VISEFFECT_HasEnded]
	Next

	Return $l_ai2_VisEffects
EndFunc

; ========== Public: Get agent visible effect count ==========
Func UAI_GetAgentVisibleEffectCount($a_i_AgentID)
	Local $l_i_Index = UAI_GetIndexByID($a_i_AgentID)
	If $l_i_Index = 0 Then Return 0
	Return $g_ai_VisEffectsCount[$l_i_Index]
EndFunc

; ========== Public: Get player visible effect count ==========
Func UAI_GetPlayerVisibleEffectCount()
	Return $g_i_PlayerVisEffectsCount
EndFunc

Func UAI_GetFeederEnchOnTop()
    Local $l_i_EffectCount = $g_i_PlayerEffectsCount
    If $l_i_EffectCount = 0 Then Return False

    Local $l_i_Timestamp = 0
    Local $l_i_SkillID = 0

    Local $l_ai_FeederEnchantments[8] = [ _
        $GC_I_SKILL_ID_GRENTHS_FINGERS, _
        $GC_I_SKILL_ID_AURA_OF_THORNS, _
        $GC_I_SKILL_ID_BALTHAZARS_RAGE, _
        $GC_I_SKILL_ID_DUST_CLOAK, _
        $GC_I_SKILL_ID_STAGGERING_FORCE, _
        $GC_I_SKILL_ID_PIOUS_RENEWAL, _
        $GC_I_SKILL_ID_EREMITES_ZEAL, _
        $GC_I_SKILL_ID_ZEALOUS_RENEWAL _
    ]

    ; Find the newest Dervish enchantment
    For $i = 0 To $l_i_EffectCount - 1
        Local $l_i_CurrentSkillID = $g_amx3_PlayerEffects[0][$i][$GC_UAI_EFFECT_SkillID]
        ; A skill id the client knows but the static table does not yet (added by a patch)
        If $l_i_CurrentSkillID < 0 Or $l_i_CurrentSkillID >= $GC_I_SKILL_DATA_ROWS Then ContinueLoop
        If $GC_AMX2_SKILL_DATA[$l_i_CurrentSkillID][$GC_I_SKILL_PROFESSION] <> $GC_I_PROFESSION_DERVISH Then ContinueLoop
        If $GC_AMX2_SKILL_DATA[$l_i_CurrentSkillID][$GC_I_SKILL_TYPE] <> $GC_I_SKILL_TYPE_ENCHANTMENT Then ContinueLoop
        Local $l_i_CurrentTimestamp = $g_amx3_PlayerEffects[0][$i][$GC_UAI_EFFECT_Timestamp]
        If $l_i_CurrentTimestamp > $l_i_Timestamp Then
            $l_i_Timestamp = $l_i_CurrentTimestamp
            $l_i_SkillID = $l_i_CurrentSkillID
        EndIf
    Next

    If $l_i_SkillID = 0 Then Return False
    If _ArrayBinarySearch($l_ai_FeederEnchantments, $l_i_SkillID) < 0 Then Return False
    If $g_i_LastFeederEnchTimestamp = $l_i_Timestamp Then Return False

	$g_i_LastFeederEnchTimestamp = $l_i_Timestamp
    Return True
EndFunc

Func UAI_PlayerHasEffectType($a_s_EffectType = "")
	Local $l_i_EffectCount = $g_i_PlayerEffectsCount
	If $l_i_EffectCount = 0 Then Return False

	Local $l_i_EffectType = ""
	Switch $a_s_EffectType
		Case "HasStance"
			$l_i_EffectType = $GC_I_SKILL_TYPE_STANCE
		Case "HasGlyph"
			$l_i_EffectType = $GC_I_SKILL_TYPE_GLYPH
		Case "HasPreparation"
			$l_i_EffectType = $GC_I_SKILL_TYPE_PREPARATION
		Case Else
			Return SetError(1, 0, False)
	EndSwitch

	For $i = ($l_i_EffectCount - 1) To 0 Step -1
		Local $l_i_CurrentSkillID = $g_amx3_PlayerEffects[0][$i][$GC_UAI_EFFECT_SkillID]
		; A skill id the client knows but the static table does not yet (added by a patch)
		If $l_i_CurrentSkillID < 0 Or $l_i_CurrentSkillID >= $GC_I_SKILL_DATA_ROWS Then ContinueLoop
		Local $l_i_SkillType = $GC_AMX2_SKILL_DATA[$l_i_CurrentSkillID][$GC_I_SKILL_TYPE]
		If $l_i_SkillType = $l_i_EffectType Then Return SetExtended($l_i_CurrentSkillID, True)
	Next

	Return False
EndFunc