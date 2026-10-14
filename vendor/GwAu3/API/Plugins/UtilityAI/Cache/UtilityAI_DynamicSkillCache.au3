#include-once

; ========== Dynamic Skill data ==========
Global Enum $GC_UAI_DYNAMIC_SKILL_Adrenaline, _
	$GC_UAI_DYNAMIC_SKILL_AdrenalineB, _
	$GC_UAI_DYNAMIC_SKILL_IsRecharged, _
	$GC_UAI_DYNAMIC_SKILL_SkillID, _
	$GC_UAI_DYNAMIC_SKILL_Event, _
	$GC_UAI_DYNAMIC_SKILL_RechargeTime, _
	$GC_UAI_DYNAMIC_SKILL_COUNT

Global Const $GC_UAI_DYNAMIC_SKILL_SLOTS = 8

Global $g_amx2_DynamicSkillCache[$GC_UAI_DYNAMIC_SKILL_SLOTS + 1][$GC_UAI_DYNAMIC_SKILL_COUNT]

; ========== Shared struct template ==========
Func UAI_GetDynamicSkillStruct()
	Static $s = Memory_CreateArrayStructure( _
		"dword Adrenaline[0x0];" & _
		"dword AdrenalineB[0x4];" & _
		"dword Timestamp[0x8];" & _
		"dword SkillID[0xC];" & _
		"dword Event[0x10]", _
		0x14)
	Return $s
EndFunc

; ========== Cache Dynamic Skill data ==========
Func UAI_CacheDynamicSkillbarInfo()
	; Full reset: fresh zero-filled array each frame
	Global $g_amx2_DynamicSkillCache[$GC_UAI_DYNAMIC_SKILL_SLOTS + 1][$GC_UAI_DYNAMIC_SKILL_COUNT]

	If $g_p_StaticSkillbarPtr = 0 Then Return SetError(1, 0, False)

	Local $l_amx2_AllSkills = Memory_ReadArrayStruct($g_p_StaticSkillbarPtr + 0x4, $GC_UAI_DYNAMIC_SKILL_SLOTS, UAI_GetDynamicSkillStruct())
	If @error Then Return SetError(2, 0, False)

	Local $l_i_SkillTimerSigned = Utils_MakeInt32(Skill_GetSkillTimer())

	For $i = 1 To $GC_UAI_DYNAMIC_SKILL_SLOTS
		Local $l_i_Idx = $i - 1

		$g_amx2_DynamicSkillCache[$i][$GC_UAI_DYNAMIC_SKILL_Adrenaline]  = $l_amx2_AllSkills[$l_i_Idx][0]
		$g_amx2_DynamicSkillCache[$i][$GC_UAI_DYNAMIC_SKILL_AdrenalineB] = $l_amx2_AllSkills[$l_i_Idx][1]
		$g_amx2_DynamicSkillCache[$i][$GC_UAI_DYNAMIC_SKILL_SkillID]     = $l_amx2_AllSkills[$l_i_Idx][3]
		$g_amx2_DynamicSkillCache[$i][$GC_UAI_DYNAMIC_SKILL_Event]       = $l_amx2_AllSkills[$l_i_Idx][4]

		Local $l_i_RechargeTimestamp = $l_amx2_AllSkills[$l_i_Idx][2]
		If $l_i_RechargeTimestamp = 0 Then
			$g_amx2_DynamicSkillCache[$i][$GC_UAI_DYNAMIC_SKILL_IsRecharged]  = True
			$g_amx2_DynamicSkillCache[$i][$GC_UAI_DYNAMIC_SKILL_RechargeTime] = 0
			ContinueLoop
		EndIf

		Local $l_i_TimeRemaining = Utils_MakeInt32($l_i_RechargeTimestamp) - $l_i_SkillTimerSigned
		If $l_i_TimeRemaining <= 0 Then
			$g_amx2_DynamicSkillCache[$i][$GC_UAI_DYNAMIC_SKILL_IsRecharged]  = True
			$g_amx2_DynamicSkillCache[$i][$GC_UAI_DYNAMIC_SKILL_RechargeTime] = 0
		Else
			$g_amx2_DynamicSkillCache[$i][$GC_UAI_DYNAMIC_SKILL_IsRecharged]  = False
			$g_amx2_DynamicSkillCache[$i][$GC_UAI_DYNAMIC_SKILL_RechargeTime] = $l_i_TimeRemaining
		EndIf
	Next

	Return True
EndFunc

Func UAI_GetDynamicSkillInfo($a_i_Slot, $a_i_InfoType)
	If $a_i_Slot < 1 Or $a_i_Slot > $GC_UAI_DYNAMIC_SKILL_SLOTS Then Return 0
	If $a_i_InfoType < 0 Or $a_i_InfoType >= $GC_UAI_DYNAMIC_SKILL_COUNT Then Return 0
	Return $g_amx2_DynamicSkillCache[$a_i_Slot][$a_i_InfoType]
EndFunc