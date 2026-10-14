#include-once

#Region Agent Helpers
; Convert AgentID (-2 = player, -1 = target, else = actual ID)
Func UAI_ConvertAgentID($a_i_AgentID)
    Return Agent_ConvertID($a_i_AgentID)
EndFunc
#EndRegion

#Region Find Agent
Func UAI_FindAgentByPlayerNumber($a_v_PlayerNumber, $a_i_AgentID = -2, $a_i_Range = 5000, $a_s_Filter = "")
    Local $l_i_RefID = UAI_ConvertAgentID($a_i_AgentID)
    Local $l_b_IsArray = IsArray($a_v_PlayerNumber)

    For $i = 1 To $g_i_AgentCacheCount
        Local $l_i_AgentID = UAI_GetAgentInfo($i, $GC_UAI_AGENT_ID)

        If $l_i_AgentID = $l_i_RefID Then ContinueLoop

        Local $l_i_PlayerNum = UAI_GetAgentInfo($i, $GC_UAI_AGENT_PlayerNumber)

        If $l_b_IsArray Then
            Local $l_b_Match = False
            For $j = 0 To UBound($a_v_PlayerNumber) - 1
                If $l_i_PlayerNum = $a_v_PlayerNumber[$j] Then
                    $l_b_Match = True
                    ExitLoop
                EndIf
            Next
            If Not $l_b_Match Then ContinueLoop
        Else
            If $l_i_PlayerNum <> $a_v_PlayerNumber Then ContinueLoop
        EndIf

        If $a_s_Filter <> "" And Not _ApplyFilters($l_i_AgentID, $a_s_Filter) Then ContinueLoop

        Local $l_f_Distance = UAI_GetAgentInfo($i, $GC_UAI_AGENT_Distance)

        If $l_f_Distance <= $a_i_Range Then Return $l_i_AgentID
    Next

    Return 0
EndFunc
#EndRegion

#Region GetAgents
; Count agents matching filter within range (using cache)
; Distance is calculated from $a_i_AgentID (not always from player)
Func UAI_CountAgents($a_i_AgentID = -2, $a_f_Range = 1320, $a_s_Filter = "")
    Local $l_i_Count = 0
    Local $l_i_RefID = UAI_ConvertAgentID($a_i_AgentID)

    ; Get reference position
    Local $l_f_RefX, $l_f_RefY
    If $l_i_RefID = UAI_GetPlayerInfo($GC_UAI_AGENT_ID) Then
        $l_f_RefX = UAI_GetPlayerInfo($GC_UAI_AGENT_X)
        $l_f_RefY = UAI_GetPlayerInfo($GC_UAI_AGENT_Y)
    Else
        $l_f_RefX = UAI_GetAgentInfoByID($l_i_RefID, $GC_UAI_AGENT_X)
        $l_f_RefY = UAI_GetAgentInfoByID($l_i_RefID, $GC_UAI_AGENT_Y)
    EndIf

    Local $l_f_RangeSquared = $a_f_Range * $a_f_Range

    For $i = 1 To $g_i_AgentCacheCount
        Local $l_i_AgentID = UAI_GetAgentInfo($i, $GC_UAI_AGENT_ID)

        If $l_i_AgentID = $l_i_RefID Then ContinueLoop

        Local $l_f_AgentX = UAI_GetAgentInfo($i, $GC_UAI_AGENT_X)
        Local $l_f_AgentY = UAI_GetAgentInfo($i, $GC_UAI_AGENT_Y)
        Local $l_f_DX = $l_f_AgentX - $l_f_RefX
        Local $l_f_DY = $l_f_AgentY - $l_f_RefY
        Local $l_f_DistSquared = $l_f_DX * $l_f_DX + $l_f_DY * $l_f_DY

        If $l_f_DistSquared > $l_f_RangeSquared Then ContinueLoop

        If $a_s_Filter <> "" And Not _ApplyFilters($l_i_AgentID, $a_s_Filter) Then ContinueLoop

        $l_i_Count += 1
    Next

    Return $l_i_Count
EndFunc

; Checks if agent matching filter within range (using cache)
; Distance is calculated from $a_i_AgentID (not always from player)
Func UAI_IsAgentInRange($a_i_AgentID = -2, $a_f_Range = 1320, $a_s_Filter = "")
    Local $l_i_RefID = UAI_ConvertAgentID($a_i_AgentID)

    Local $l_f_RefX, $l_f_RefY
    If $l_i_RefID = UAI_GetPlayerInfo($GC_UAI_AGENT_ID) Then
        $l_f_RefX = UAI_GetPlayerInfo($GC_UAI_AGENT_X)
        $l_f_RefY = UAI_GetPlayerInfo($GC_UAI_AGENT_Y)
    Else
        $l_f_RefX = UAI_GetAgentInfoByID($l_i_RefID, $GC_UAI_AGENT_X)
        $l_f_RefY = UAI_GetAgentInfoByID($l_i_RefID, $GC_UAI_AGENT_Y)
    EndIf

    Local $l_f_RangeSquared = $a_f_Range * $a_f_Range

    For $i = 1 To $g_i_AgentCacheCount
        Local $l_i_AgentID = UAI_GetAgentInfo($i, $GC_UAI_AGENT_ID)

        If $l_i_AgentID = $l_i_RefID Then ContinueLoop

        Local $l_f_AgentX = UAI_GetAgentInfo($i, $GC_UAI_AGENT_X)
        Local $l_f_AgentY = UAI_GetAgentInfo($i, $GC_UAI_AGENT_Y)
        Local $l_f_DX = $l_f_AgentX - $l_f_RefX
        Local $l_f_DY = $l_f_AgentY - $l_f_RefY
        Local $l_f_DistSquared = $l_f_DX * $l_f_DX + $l_f_DY * $l_f_DY

        If $l_f_DistSquared > $l_f_RangeSquared Then ContinueLoop

        If $a_s_Filter <> "" And Not _ApplyFilters($l_i_AgentID, $a_s_Filter) Then ContinueLoop

        Return True
    Next

    Return False
EndFunc

; Get nearest agent matching filter within range (using cache)
Func UAI_GetNearestAgent($a_i_AgentID = -2, $a_f_Range = 1320, $a_s_Filter = "")
    Local $l_i_NearestID = 0
    Local $l_f_NearestDist = 0x7FFFFFFF
    Local $l_i_RefID = UAI_ConvertAgentID($a_i_AgentID)

    For $i = 1 To $g_i_AgentCacheCount
        Local $l_f_Distance = UAI_GetAgentInfo($i, $GC_UAI_AGENT_Distance)
        If $l_f_Distance > $a_f_Range Then ContinueLoop

		Local $l_i_AgentID = UAI_GetAgentInfo($i, $GC_UAI_AGENT_ID)
        If $l_i_AgentID = $l_i_RefID Then ContinueLoop

        If $a_s_Filter <> "" And Not _ApplyFilters($l_i_AgentID, $a_s_Filter) Then ContinueLoop

        If $l_f_Distance < $l_f_NearestDist Then
            $l_f_NearestDist = $l_f_Distance
            $l_i_NearestID = $l_i_AgentID
        EndIf
    Next

    Return $l_i_NearestID
EndFunc

; Get farthest agent matching filter within range (using cache)
Func UAI_GetFarthestAgent($a_i_AgentID = -2, $a_f_Range = 1320, $a_s_Filter = "")
    Local $l_i_FarthestID = 0
    Local $l_f_FarthestDist = 0
    Local $l_i_RefID = UAI_ConvertAgentID($a_i_AgentID)

    For $i = 1 To $g_i_AgentCacheCount
		Local $l_f_Distance = UAI_GetAgentInfo($i, $GC_UAI_AGENT_Distance)
        If $l_f_Distance > $a_f_Range Then ContinueLoop

		Local $l_i_AgentID = UAI_GetAgentInfo($i, $GC_UAI_AGENT_ID)
        If $l_i_AgentID = $l_i_RefID Then ContinueLoop

        If $a_s_Filter <> "" And Not _ApplyFilters($l_i_AgentID, $a_s_Filter) Then ContinueLoop

        If $l_f_Distance > $l_f_FarthestDist Then
            $l_f_FarthestDist = $l_f_Distance
            $l_i_FarthestID = $l_i_AgentID
        EndIf
    Next

    Return $l_i_FarthestID
EndFunc
#EndRegion GetAgents

#Region BestTarget
; Get agent with lowest property value (HP, Energy, etc.)
Func UAI_GetAgentLowest($a_i_AgentID = -2, $a_f_Range = 1320, $a_i_Property = $GC_UAI_AGENT_HP, $a_s_CustomFilter = "")
	Local $l_f_LowestValue = 0x7FFFFFFF
	Local $l_i_LowestAgent = 0
	Local $l_i_RefID = UAI_ConvertAgentID($a_i_AgentID)

	If $g_i_AgentCacheCount = 0 Then Return 0

	For $i = 1 To $g_i_AgentCacheCount
		Local $l_f_Distance = UAI_GetAgentInfo($i, $GC_UAI_AGENT_Distance)
		If $l_f_Distance > $a_f_Range Then ContinueLoop

		Local $l_i_AgentID = UAI_GetAgentInfo($i, $GC_UAI_AGENT_ID)

		If $a_s_CustomFilter <> "" And Not _ApplyFilters($l_i_AgentID, $a_s_CustomFilter) Then ContinueLoop

		Local $l_v_Value = UAI_GetAgentInfo($i, $a_i_Property)

		If $l_v_Value < $l_f_LowestValue Then
			$l_f_LowestValue = $l_v_Value
			$l_i_LowestAgent = $l_i_AgentID
		EndIf
	Next

	Return $l_i_LowestAgent
EndFunc

; Get agent with highest property value
Func UAI_GetAgentHighest($a_i_AgentID = -2, $a_f_Range = 1320, $a_i_Property = $GC_UAI_AGENT_HP, $a_s_CustomFilter = "")
	Local $l_f_HighestValue = -1
	Local $l_i_HighestAgent = 0
	Local $l_i_RefID = UAI_ConvertAgentID($a_i_AgentID)

	If $g_i_AgentCacheCount = 0 Then Return 0

	For $i = 1 To $g_i_AgentCacheCount
		Local $l_f_Distance = UAI_GetAgentInfo($i, $GC_UAI_AGENT_Distance)
		If $l_f_Distance > $a_f_Range Then ContinueLoop

		Local $l_i_AgentID = UAI_GetAgentInfo($i, $GC_UAI_AGENT_ID)

		If $a_s_CustomFilter <> "" And Not _ApplyFilters($l_i_AgentID, $a_s_CustomFilter) Then ContinueLoop

		Local $l_v_Value = UAI_GetAgentInfo($i, $a_i_Property)

		If $l_v_Value > $l_f_HighestValue Then
			$l_f_HighestValue = $l_v_Value
			$l_i_HighestAgent = $l_i_AgentID
		EndIf
	Next

	Return $l_i_HighestAgent
EndFunc

Func UAI_GetBestSingleTarget($a_i_AgentID = -2, $a_f_Range = 1320, $a_i_Property = $GC_UAI_AGENT_HP, $a_s_CustomFilter = "")
	If $g_i_FightMode = $g_i_FinisherMode Then Return UAI_GetAgentLowest($a_i_AgentID, $a_f_Range, $a_i_Property, $a_s_CustomFilter)
	If $g_i_FightMode = $g_i_PressureMode Then Return UAI_GetAgentHighest($a_i_AgentID, $a_f_Range, $a_i_Property, $a_s_CustomFilter)
	Return 0
EndFunc

; Get best AOE target based on group size first, then average HP as tiebreaker.
; Priority: 1) Most agents in AOE range, 2) HP comparison based on fight mode.
; FinisherMode (0): lowest average HP wins. PressureMode (1): highest average HP wins.
; Returns the agent at the center of the best group.
;
; Strategy: filter the cache into flat arrays once (filter runs O(N), not O(N^2)),
; then accumulate every agent's group stats in a single symmetric pairwise pass
; (each in-AOE pair updates both agents), giving O(M^2/2) over the filtered set M.
Func UAI_GetBestAOETarget($a_i_AgentID = -2, $a_f_Range = 1320, $a_f_AOERange = $GC_I_RANGE_ADJACENT, $a_s_CustomFilter = "")
    If $g_i_AgentCacheCount = 0 Then Return 0

    Local $l_af_CoordsX[$g_i_AgentCacheCount + 1]
    Local $l_af_CoordsY[$g_i_AgentCacheCount + 1]
    Local $l_af_AgentHP[$g_i_AgentCacheCount + 1]
    Local $l_ai_AgentID[$g_i_AgentCacheCount + 1]
    Local $l_ab_Eligible[$g_i_AgentCacheCount + 1]
    Local $l_ai_Count[$g_i_AgentCacheCount + 1]
    Local $l_af_SumHP[$g_i_AgentCacheCount + 1]
    Local $l_i_M = 0

    For $i = 1 To $g_i_AgentCacheCount
        Local $l_i_AgentID = UAI_GetAgentInfo($i, $GC_UAI_AGENT_ID)
        If $a_s_CustomFilter <> "" And Not _ApplyFilters($l_i_AgentID, $a_s_CustomFilter) Then ContinueLoop

        $l_i_M += 1
        $l_ab_Eligible[$l_i_M] = (UAI_GetAgentInfo($i, $GC_UAI_AGENT_Distance) <= $a_f_Range)
        $l_af_CoordsX[$l_i_M] = UAI_GetAgentInfo($i, $GC_UAI_AGENT_X)
        $l_af_CoordsY[$l_i_M] = UAI_GetAgentInfo($i, $GC_UAI_AGENT_Y)
        $l_af_AgentHP[$l_i_M] = UAI_GetAgentInfo($i, $GC_UAI_AGENT_HP)
        $l_ai_AgentID[$l_i_M] = $l_i_AgentID
        $l_ai_Count[$l_i_M]  = 1 ; counts itself
        $l_af_SumHP[$l_i_M]  = $l_af_AgentHP[$l_i_M]
    Next
    If $l_i_M = 0 Then Return 0

    Local $l_f_AOESq = $a_f_AOERange * $a_f_AOERange
    For $a = 1 To $l_i_M - 1
        Local $l_f_X = $l_af_CoordsX[$a]
        Local $l_f_Y = $l_af_CoordsY[$a]
        Local $l_f_HP = $l_af_AgentHP[$a]
        For $b = $a + 1 To $l_i_M
            Local $l_f_DX = $l_af_CoordsX[$b] - $l_f_X
            Local $l_f_DY = $l_af_CoordsY[$b] - $l_f_Y
            If ($l_f_DX * $l_f_DX + $l_f_DY * $l_f_DY) > $l_f_AOESq Then ContinueLoop

            $l_ai_Count[$a] += 1
            $l_af_SumHP[$a] += $l_af_AgentHP[$b]
            $l_ai_Count[$b] += 1
            $l_af_SumHP[$b] += $l_f_HP
        Next
    Next

    Local $l_b_Finisher = ($g_i_FightMode = $g_i_FinisherMode)
    Local $l_i_BestAgent = 0
    Local $l_i_BestCount = 0
    Local $l_f_BestAvgHP = $l_b_Finisher ? 0x7FFFFFFF : 0

    For $m = 1 To $l_i_M
        If Not $l_ab_Eligible[$m] Then ContinueLoop

        Local $l_i_Count = $l_ai_Count[$m]
        Local $l_f_AvgHP = $l_af_SumHP[$m] / $l_i_Count

        If $l_i_Count > $l_i_BestCount Then
            $l_i_BestCount = $l_i_Count
            $l_f_BestAvgHP = $l_f_AvgHP
            $l_i_BestAgent = $l_ai_AgentID[$m]
        ElseIf $l_i_Count = $l_i_BestCount Then
            Local $l_b_BetterHP = $l_b_Finisher ? ($l_f_AvgHP < $l_f_BestAvgHP) : ($l_f_AvgHP > $l_f_BestAvgHP)
            If $l_b_BetterHP Then
                $l_f_BestAvgHP = $l_f_AvgHP
                $l_i_BestAgent = $l_ai_AgentID[$m]
            EndIf
        EndIf
    Next

    Return $l_i_BestAgent
EndFunc

; Get best single target considering armor for damage type
; $a_s_DamageType: "Elemental" / "Physical" / etc.
; Score = HP / DamageMultiplier (lower = easier to kill with this damage type)
Func UAI_GetBestTargetByDamageType($a_i_AgentID = -2, $a_f_Range = 1320, $a_s_DamageType = "Elemental", $a_s_CustomFilter = "")
	Local $l_i_BestAgent = 0
	Local $l_f_BestScore = ($g_i_FightMode = $g_i_FinisherMode) ? 0x7FFFFFFF : 0
	Local $l_i_RefID = UAI_ConvertAgentID($a_i_AgentID)

	If $g_i_AgentCacheCount = 0 Then Return 0

	For $i = 1 To $g_i_AgentCacheCount
		Local $l_i_AgentID = UAI_GetAgentInfo($i, $GC_UAI_AGENT_ID)

		If $l_i_AgentID = $l_i_RefID Then ContinueLoop

		Local $l_f_Distance = UAI_GetAgentInfo($i, $GC_UAI_AGENT_Distance)
		If $l_f_Distance > $a_f_Range Then ContinueLoop

		If $a_s_CustomFilter <> "" And Not _ApplyFilters($l_i_AgentID, $a_s_CustomFilter) Then ContinueLoop

		Local $l_f_HP = UAI_GetAgentInfo($i, $GC_UAI_AGENT_HP)
		Local $l_f_Score = _GetArmorScore($l_i_AgentID, $l_f_HP, $a_s_DamageType)

		If $g_i_FightMode = $g_i_FinisherMode Then
			If $l_f_Score < $l_f_BestScore Then
				$l_f_BestScore = $l_f_Score
				$l_i_BestAgent = $l_i_AgentID
			EndIf
		Else ; Pressure mode
			If $l_f_Score > $l_f_BestScore Then
				$l_f_BestScore = $l_f_Score
				$l_i_BestAgent = $l_i_AgentID
			EndIf
		EndIf
	Next

	Return $l_i_BestAgent
EndFunc

; Get best AOE target considering armor for damage type.
; Priority: 1) Most agents in AOE range, 2) Average effective-HP score based on armor.
; Same flat-array + symmetric-pass strategy as UAI_GetBestAOETarget, but each agent's
; armor score is computed ONCE up front (O(M)).
Func UAI_GetBestAOETargetByDamageType($a_i_AgentID = -2, $a_f_Range = 1320, $a_f_AOERange = $GC_I_RANGE_ADJACENT, $a_s_DamageType = "Elemental", $a_s_CustomFilter = "")
	If $g_i_AgentCacheCount = 0 Then Return 0

	Local $l_af_CoordsX[$g_i_AgentCacheCount + 1]
	Local $l_af_CoordsY[$g_i_AgentCacheCount + 1]
	Local $l_af_Score[$g_i_AgentCacheCount + 1]
	Local $l_ai_AgentID[$g_i_AgentCacheCount + 1]
	Local $l_ab_Eligible[$g_i_AgentCacheCount + 1]
	Local $l_ai_Count[$g_i_AgentCacheCount + 1]
	Local $l_af_SumScore[$g_i_AgentCacheCount + 1]
	Local $l_i_M = 0

	For $i = 1 To $g_i_AgentCacheCount
		Local $l_i_AgentID = UAI_GetAgentInfo($i, $GC_UAI_AGENT_ID)
		If $a_s_CustomFilter <> "" And Not _ApplyFilters($l_i_AgentID, $a_s_CustomFilter) Then ContinueLoop

		$l_i_M += 1
		$l_ab_Eligible[$l_i_M] = (UAI_GetAgentInfo($i, $GC_UAI_AGENT_Distance) <= $a_f_Range)
		$l_af_CoordsX[$l_i_M]  = UAI_GetAgentInfo($i, $GC_UAI_AGENT_X)
		$l_af_CoordsY[$l_i_M]  = UAI_GetAgentInfo($i, $GC_UAI_AGENT_Y)
		Local $l_f_HP = UAI_GetAgentInfo($i, $GC_UAI_AGENT_HP)
		$l_af_Score[$l_i_M]    = _GetArmorScore($l_i_AgentID, $l_f_HP, $a_s_DamageType) ; armor lookup ONCE per agent
		$l_ai_AgentID[$l_i_M]  = $l_i_AgentID
		$l_ai_Count[$l_i_M]    = 1
		$l_af_SumScore[$l_i_M] = $l_af_Score[$l_i_M]
	Next
	If $l_i_M = 0 Then Return 0

	Local $l_f_AOESq = $a_f_AOERange * $a_f_AOERange
	For $a = 1 To $l_i_M - 1
		Local $l_f_X = $l_af_CoordsX[$a]
		Local $l_f_Y = $l_af_CoordsY[$a]
		Local $l_f_Sc = $l_af_Score[$a]
		For $b = $a + 1 To $l_i_M
			Local $l_f_DX = $l_af_CoordsX[$b] - $l_f_X
			Local $l_f_DY = $l_af_CoordsY[$b] - $l_f_Y
			If ($l_f_DX * $l_f_DX + $l_f_DY * $l_f_DY) > $l_f_AOESq Then ContinueLoop

			$l_ai_Count[$a] += 1
			$l_af_SumScore[$a] += $l_af_Score[$b]
			$l_ai_Count[$b] += 1
			$l_af_SumScore[$b] += $l_f_Sc
		Next
	Next

	Local $l_b_Finisher = ($g_i_FightMode = $g_i_FinisherMode)
	Local $l_i_BestAgent = 0
	Local $l_i_BestCount = 0
	Local $l_f_BestAvgScore = $l_b_Finisher ? 0x7FFFFFFF : 0

	For $m = 1 To $l_i_M
		If Not $l_ab_Eligible[$m] Then ContinueLoop

		Local $l_i_Count = $l_ai_Count[$m]
		Local $l_f_AvgScore = $l_af_SumScore[$m] / $l_i_Count

		If $l_i_Count > $l_i_BestCount Then
			$l_i_BestCount = $l_i_Count
			$l_f_BestAvgScore = $l_f_AvgScore
			$l_i_BestAgent = $l_ai_AgentID[$m]
		ElseIf $l_i_Count = $l_i_BestCount Then
			Local $l_b_Better = $l_b_Finisher ? ($l_f_AvgScore < $l_f_BestAvgScore) : ($l_f_AvgScore > $l_f_BestAvgScore)
			If $l_b_Better Then
				$l_f_BestAvgScore = $l_f_AvgScore
				$l_i_BestAgent = $l_ai_AgentID[$m]
			EndIf
		EndIf
	Next

	Return $l_i_BestAgent
EndFunc

; Internal: Calculate armor-adjusted score for an agent
Func _GetArmorScore($a_i_AgentID, $a_f_HP, $a_s_DamageType)
	Local $l_i_Armor
	Switch $a_s_DamageType
		Case "Elemental", "Fire", "Cold", "Lightning", "Earth"
			$l_i_Armor = UAI_GetElementalArmor($a_i_AgentID)
		Case "Physical", "Blunt", "Piercing", "Slashing"
			$l_i_Armor = UAI_GetPhysicalArmor($a_i_AgentID)
		Case Else
			$l_i_Armor = UAI_GetBaseArmor($a_i_AgentID)
	EndSwitch

	Local $l_f_DamageMult = UAI_GetDamageMultiplier($l_i_Armor)
	Return $a_f_HP / $l_f_DamageMult
EndFunc
#EndRegion

#Region Ward
Func _UAI_CountAlliesInRange(ByRef $a_af_X, ByRef $a_af_Y, $a_i_Count, $a_f_CX, $a_f_CY, $a_f_RangeSq)
	Local $l_i_InRange = 0
	For $i = 1 To $a_i_Count
		Local $l_f_DX = $a_af_X[$i] - $a_f_CX
		Local $l_f_DY = $a_af_Y[$i] - $a_f_CY
		If ($l_f_DX * $l_f_DX + $l_f_DY * $l_f_DY) <= $a_f_RangeSq Then $l_i_InRange += 1
	Next
	Return $l_i_InRange
EndFunc   ;==>_UAI_CountAlliesInRange

; From the ally set, find the position whose range-disk covers the most allies.
; Candidate points = every ally position PLUS every pairwise midpoint.
; Coverage ties resolve toward the anchor (FromX/FromY), so among equally good spots the nearest one wins.
Func _UAI_BestCoveragePosition(ByRef $a_af_X, ByRef $a_af_Y, $a_i_Count, $a_f_Range, $a_f_FromX, $a_f_FromY)
	Local $l_av_Result[3] = [0, 0, 0]
	If $a_i_Count = 0 Then Return $l_av_Result

	Local $l_f_RangeSq = $a_f_Range * $a_f_Range

	Local $l_i_MaxCand = $a_i_Count + ($a_i_Count * ($a_i_Count - 1)) / 2
	Local $l_af_CandX[$l_i_MaxCand + 1], $l_af_CandY[$l_i_MaxCand + 1]
	Local $l_i_Cand = 0
	For $c = 1 To $a_i_Count
		$l_i_Cand += 1
		$l_af_CandX[$l_i_Cand] = $a_af_X[$c]
		$l_af_CandY[$l_i_Cand] = $a_af_Y[$c]
	Next
	For $a = 1 To $a_i_Count - 1
		For $b = $a + 1 To $a_i_Count
			$l_i_Cand += 1
			$l_af_CandX[$l_i_Cand] = ($a_af_X[$a] + $a_af_X[$b]) * 0.5
			$l_af_CandY[$l_i_Cand] = ($a_af_Y[$a] + $a_af_Y[$b]) * 0.5
		Next
	Next

	Local $l_f_BestX = 0, $l_f_BestY = 0
	Local $l_i_BestCover = 0, $l_f_BestDistSq = 0
	For $k = 1 To $l_i_Cand
		Local $l_f_CX = $l_af_CandX[$k], $l_f_CY = $l_af_CandY[$k]
		Local $l_i_Cover = _UAI_CountAlliesInRange($a_af_X, $a_af_Y, $a_i_Count, $l_f_CX, $l_f_CY, $l_f_RangeSq)
		If $l_i_Cover < 1 Then ContinueLoop

		Local $l_f_DDX = $l_f_CX - $a_f_FromX, $l_f_DDY = $l_f_CY - $a_f_FromY
		Local $l_f_DistSq = $l_f_DDX * $l_f_DDX + $l_f_DDY * $l_f_DDY

		If $l_i_Cover > $l_i_BestCover Or ($l_i_Cover = $l_i_BestCover And $l_f_DistSq < $l_f_BestDistSq) Then
			$l_i_BestCover = $l_i_Cover
			$l_f_BestDistSq = $l_f_DistSq
			$l_f_BestX = $l_f_CX
			$l_f_BestY = $l_f_CY
		EndIf
	Next

	If $l_i_BestCover < 1 Then Return $l_av_Result
	$l_av_Result[0] = $l_f_BestX
	$l_av_Result[1] = $l_f_BestY
	$l_av_Result[2] = $l_i_BestCover
	Return $l_av_Result
EndFunc   ;==>_UAI_BestCoveragePosition

; Gather living allies from the agent cache and resolve the best ward position.
; Returns [X, Y, Count]; Count 0 means no allies found.
Func UAI_GetBestWardPosition($a_f_WardRange = $GC_I_RANGE_AREA)
	Local $l_af_X[$g_i_AgentCacheCount + 1]
	Local $l_af_Y[$g_i_AgentCacheCount + 1]
	Local $l_i_Count = 0

	For $i = 1 To $g_i_AgentCacheCount
		Local $l_i_AgentID = UAI_GetAgentInfo($i, $GC_UAI_AGENT_ID)
		If Not UAI_Filter_IsLivingAlly($l_i_AgentID) Then ContinueLoop
		If Not UAI_Filter_ExcludeMe($l_i_AgentID) Then ContinueLoop
		$l_i_Count += 1
		$l_af_X[$l_i_Count] = UAI_GetAgentInfo($i, $GC_UAI_AGENT_X)
		$l_af_Y[$l_i_Count] = UAI_GetAgentInfo($i, $GC_UAI_AGENT_Y)
	Next

	Local $l_f_MeX = UAI_GetPlayerInfo($GC_UAI_AGENT_X)
	Local $l_f_MeY = UAI_GetPlayerInfo($GC_UAI_AGENT_Y)

	Return _UAI_BestCoveragePosition($l_af_X, $l_af_Y, $l_i_Count, $a_f_WardRange, $l_f_MeX, $l_f_MeY)
EndFunc   ;==>UAI_GetBestWardPosition

; Gather living enemies from the agent cache and resolve the best ward position.
; Returns [X, Y, Count]; Count 0 means no enemies found.
Func UAI_GetBestOffensiveWardPosition($a_f_WardRange = $GC_I_RANGE_AREA)
	Local $l_af_X[$g_i_AgentCacheCount + 1]
	Local $l_af_Y[$g_i_AgentCacheCount + 1]
	Local $l_i_Count = 0

	For $i = 1 To $g_i_AgentCacheCount
		Local $l_i_AgentID = UAI_GetAgentInfo($i, $GC_UAI_AGENT_ID)
		If Not UAI_Filter_IsLivingEnemy($l_i_AgentID) Then ContinueLoop
		$l_i_Count += 1
		$l_af_X[$l_i_Count] = UAI_GetAgentInfo($i, $GC_UAI_AGENT_X)
		$l_af_Y[$l_i_Count] = UAI_GetAgentInfo($i, $GC_UAI_AGENT_Y)
	Next

	Local $l_f_MeX = UAI_GetPlayerInfo($GC_UAI_AGENT_X)
	Local $l_f_MeY = UAI_GetPlayerInfo($GC_UAI_AGENT_Y)

	Return _UAI_BestCoveragePosition($l_af_X, $l_af_Y, $l_i_Count, $a_f_WardRange, $l_f_MeX, $l_f_MeY)
EndFunc   ;==>UAI_GetBestOffensiveWardPosition

; Gather living enemies from the agent cache and resolve the best ward position.
; Returns [X, Y, Count]; Count 0 means no enemies found.
Func UAI_GetBestMartialEnemyPosition($a_f_WardRange = $GC_I_RANGE_AREA)
	Local $l_af_X[$g_i_AgentCacheCount + 1]
	Local $l_af_Y[$g_i_AgentCacheCount + 1]
	Local $l_i_Count = 0

	For $i = 1 To $g_i_AgentCacheCount
		Local $l_i_AgentID = UAI_GetAgentInfo($i, $GC_UAI_AGENT_ID)
		If Not UAI_Filter_IsLivingEnemy($l_i_AgentID) Then ContinueLoop
		If UAI_IsCaster($l_i_AgentID) Then ContinueLoop
		$l_i_Count += 1
		$l_af_X[$l_i_Count] = UAI_GetAgentInfo($i, $GC_UAI_AGENT_X)
		$l_af_Y[$l_i_Count] = UAI_GetAgentInfo($i, $GC_UAI_AGENT_Y)
	Next

	Local $l_f_MeX = UAI_GetPlayerInfo($GC_UAI_AGENT_X)
	Local $l_f_MeY = UAI_GetPlayerInfo($GC_UAI_AGENT_Y)

	Return _UAI_BestCoveragePosition($l_af_X, $l_af_Y, $l_i_Count, $a_f_WardRange, $l_f_MeX, $l_f_MeY)
EndFunc   ;==>UAI_GetBestOffensiveWardPosition

; Move to the best ward position. Returns True only when actually in range to cast,
; False if there is no position or the move times out short of it.
Func UAI_MoveToWardPosition($a_f_WardRange = $GC_I_RANGE_AREA, $a_i_WardType = $GC_I_UAI_WARDTYPE_DEFENSIVE)
	Local $l_av_BestPos[3] = [0, 0, 0]
	If $a_i_WardType = $GC_I_UAI_WARDTYPE_DEFENSIVE Then
		$l_av_BestPos = UAI_GetBestWardPosition($a_f_WardRange)
	ElseIf $a_i_WardType = $GC_I_UAI_WARDTYPE_OFFENSIVE Then 
		$l_av_BestPos = UAI_GetBestOffensiveWardPosition($a_f_WardRange)
	EndIf
	If $l_av_BestPos[2] = 0 Then Return False

	Local $l_f_TargetX = $l_av_BestPos[0]
	Local $l_f_TargetY = $l_av_BestPos[1]

	Local Const $l_f_ArrivalDistSq = 25 * 25
	Local Const $l_i_MaxTimeoutMs = 5000
	Local $l_h_Timeout = TimerInit()

	Map_Move($l_f_TargetX, $l_f_TargetY, 0) ; issue once; loop only watches for arrival
	Do
		Sleep(32)
		Local $l_f_DX = $l_f_TargetX - Agent_GetAgentInfo(-2, "X")
		Local $l_f_DY = $l_f_TargetY - Agent_GetAgentInfo(-2, "Y")
		If ($l_f_DX * $l_f_DX + $l_f_DY * $l_f_DY) < $l_f_ArrivalDistSq Then Return True
	Until TimerDiff($l_h_Timeout) >= $l_i_MaxTimeoutMs

	Return False
EndFunc   ;==>UAI_MoveToWardPosition
#EndRegion

#Region Helper
; Helper: Check if player has another Mesmer hex besides the specified one
Func UAI_PlayerHasOtherMesmerHex($a_i_ExcludeSkillID)
	If $g_i_PlayerCacheIndex < 1 Then Return False

	Local $l_i_Count = $g_ai_EffectsCount[$g_i_PlayerCacheIndex]
	For $i = 0 To $l_i_Count - 1
		Local $l_i_SkillID = $g_amx3_EffectsCache[$g_i_PlayerCacheIndex][$i][$GC_UAI_EFFECT_SkillID]
		If $l_i_SkillID = $a_i_ExcludeSkillID Then ContinueLoop

		If Skill_GetSkillInfo($l_i_SkillID, "Profession") = $GC_I_PROFESSION_MESMER Then
			Local $l_i_SkillType = Skill_GetSkillInfo($l_i_SkillID, "SkillType")
			If $l_i_SkillType = $GC_I_SKILL_TYPE_HEX Then Return True
		EndIf
	Next

	Return False
EndFunc

Func UAI_GetBestTargetByConditionCount($a_i_AgentID = -2, $a_f_Range = 1320, $a_s_CustomFilter = "")
	Local $l_i_BestAgent = 0
	Local $l_f_BestScore = ($g_i_FightMode = $g_i_FinisherMode) ? 0x7FFFFFFF : 0

	Local $l_ai_Conditions[] = [ _
			$GC_I_EFFECT_ID_BLEEDING, $GC_I_EFFECT_ID_BLINDED, $GC_I_EFFECT_ID_BURNING, _
			$GC_I_EFFECT_ID_DISEASED, $GC_I_EFFECT_ID_POISONED, $GC_I_EFFECT_ID_DAZED, _
			$GC_I_EFFECT_ID_WEAKNESS _ ; Same value as Cracked Armor
	]

	If $g_i_AgentCacheCount = 0 Then Return 0

	For $i = 1 To $g_i_AgentCacheCount
		Local $l_i_AgentID = UAI_GetAgentInfo($i, $GC_UAI_AGENT_ID)

		Local $l_f_Distance = UAI_GetAgentInfo($i, $GC_UAI_AGENT_Distance)
		If $l_f_Distance > $a_f_Range Then ContinueLoop

		If Not UAI_GetAgentInfo($i, $GC_UAI_AGENT_IsConditioned) Then ContinueLoop

		If $a_s_CustomFilter <> "" And Not _ApplyFilters($l_i_AgentID, $a_s_CustomFilter) Then ContinueLoop

		Local $l_f_HP = UAI_GetAgentInfo($i, $GC_UAI_AGENT_HP)

		Local $l_i_Count = 0
		For $condition In $l_ai_Conditions
			If UAI_AgentHasVisibleEffect($l_i_AgentID, $GC_I_EFFECT_TYPE_STATUS, $condition) Then $l_i_Count += 1
		Next

		If $l_i_Count = 0 Then ContinueLoop

		Local $l_f_Score

		If $g_i_FightMode = $g_i_FinisherMode Then
			; Prefer low HP with many conditions
			$l_f_Score = $l_f_HP / $l_i_Count

			If $l_f_Score < $l_f_BestScore Then
				$l_f_BestScore = $l_f_Score
				$l_i_BestAgent = $l_i_AgentID
			EndIf
		Else
			; Prefer high HP with many conditions
			$l_f_Score = $l_f_HP * $l_i_Count

			If $l_f_Score > $l_f_BestScore Then
				$l_f_BestScore = $l_f_Score
				$l_i_BestAgent = $l_i_AgentID
			EndIf
		EndIf
	Next

	Return $l_i_BestAgent
EndFunc

; Internal: find the corpse (dead enemy within $a_f_Range) surrounded by the most agents
; matching $a_s_MemberFilter within RANGE_AREA. Moves toward it if it isn't already nearest.
; Returns player ID when positioned to cast, else 0.
;
; Builds the corpse list and member positions in one cache pass (filters run O(N)), then
; counts members per corpse over the flat member list -> O(corpses * members) with no
; per-corpse re-filtering or ID lookups (was O(corpses * N) via UAI_CountAgents).
Func _UAI_GetBestCorpse($a_f_Range, $a_s_MemberFilter)
	Local $l_af_CorpseX[$g_i_AgentCacheCount + 1]
	Local $l_af_CorpseY[$g_i_AgentCacheCount + 1]
	Local $l_ai_CorpseID[$g_i_AgentCacheCount + 1]
	Local $l_i_CorpseCount = 0
	Local $l_i_NearestCorpse = 0
	Local $l_f_NearestDist = 0x7FFFFFFF

	Local $l_af_MemberX[$g_i_AgentCacheCount + 1]
	Local $l_af_MemberY[$g_i_AgentCacheCount + 1]
	Local $l_i_MemberCount = 0

	For $i = 1 To $g_i_AgentCacheCount
		Local $l_i_AgentID = UAI_GetAgentInfo($i, $GC_UAI_AGENT_ID)

		If UAI_Filter_IsDeadEnemy($l_i_AgentID) Then
			Local $l_f_Distance = UAI_GetAgentInfo($i, $GC_UAI_AGENT_Distance)
			If $l_f_Distance <= $a_f_Range Then
				$l_i_CorpseCount += 1
				$l_af_CorpseX[$l_i_CorpseCount]  = UAI_GetAgentInfo($i, $GC_UAI_AGENT_X)
				$l_af_CorpseY[$l_i_CorpseCount]  = UAI_GetAgentInfo($i, $GC_UAI_AGENT_Y)
				$l_ai_CorpseID[$l_i_CorpseCount] = $l_i_AgentID
				If $l_f_Distance < $l_f_NearestDist Then
					$l_f_NearestDist = $l_f_Distance
					$l_i_NearestCorpse = $l_i_AgentID
				EndIf
			EndIf
		ElseIf _ApplyFilters($l_i_AgentID, $a_s_MemberFilter) Then
			$l_i_MemberCount += 1
			$l_af_MemberX[$l_i_MemberCount] = UAI_GetAgentInfo($i, $GC_UAI_AGENT_X)
			$l_af_MemberY[$l_i_MemberCount] = UAI_GetAgentInfo($i, $GC_UAI_AGENT_Y)
		EndIf
	Next

	If $l_i_CorpseCount = 0 Then Return 0

	Local $l_f_AreaSq = $GC_I_RANGE_AREA * $GC_I_RANGE_AREA
	Local $l_i_BestCorpse = 0
	Local $l_i_BestCount = 0

	For $c = 1 To $l_i_CorpseCount
		Local $l_f_CX = $l_af_CorpseX[$c]
		Local $l_f_CY = $l_af_CorpseY[$c]
		Local $l_i_Count = 0
		For $m = 1 To $l_i_MemberCount
			Local $l_f_DX = $l_af_MemberX[$m] - $l_f_CX
			Local $l_f_DY = $l_af_MemberY[$m] - $l_f_CY
			If ($l_f_DX * $l_f_DX + $l_f_DY * $l_f_DY) <= $l_f_AreaSq Then $l_i_Count += 1
		Next
		If $l_i_Count > $l_i_BestCount Then
			$l_i_BestCount = $l_i_Count
			$l_i_BestCorpse = $l_ai_CorpseID[$c]
		EndIf
	Next

	If $l_i_BestCount = 0 Then Return 0

	If $l_i_BestCorpse = $l_i_NearestCorpse Then Return UAI_GetPlayerInfo($GC_UAI_AGENT_ID)
	If UAI_MoveTowardCorpse($l_i_BestCorpse) Then Return UAI_GetPlayerInfo($GC_UAI_AGENT_ID)
	Return 0
EndFunc

; Find best corpse for ally support wells (most living allies nearby)
Func UAI_GetBestCorpseForAllySupport($a_f_Range)
	Return _UAI_GetBestCorpse($a_f_Range, "UAI_Filter_IsLivingAlly")
EndFunc

; Find best corpse for enemy pressure wells (most living enemies nearby)
Func UAI_GetBestCorpseForEnemyPressure($a_f_Range)
	Return _UAI_GetBestCorpse($a_f_Range, "UAI_Filter_IsLivingEnemy")
EndFunc

; Move to the target corpse position so it becomes the nearest one
Func UAI_MoveTowardCorpse($a_i_TargetCorpseID)
	Local $l_f_TargetX = UAI_GetAgentInfoByID($a_i_TargetCorpseID, $GC_UAI_AGENT_X)
	Local $l_f_TargetY = UAI_GetAgentInfoByID($a_i_TargetCorpseID, $GC_UAI_AGENT_Y)

	Local $l_i_Timeout = 0
	Local Const $l_f_ArrivalDist = 80
	Local Const $l_i_MaxTimeout = 5000

	Do
		Map_Move($l_f_TargetX, $l_f_TargetY, 0)
		Sleep(32)
		$l_i_Timeout += 32

		Local $l_f_CurX = Agent_GetAgentInfo(-2, "X")
		Local $l_f_CurY = Agent_GetAgentInfo(-2, "Y")

		Local $l_f_DiffX = $l_f_TargetX - $l_f_CurX
		Local $l_f_DiffY = $l_f_TargetY - $l_f_CurY
		Local $l_f_DistToTarget = Sqrt($l_f_DiffX * $l_f_DiffX + $l_f_DiffY * $l_f_DiffY)

		If UAI_IsCorpseNearest($a_i_TargetCorpseID, $l_f_CurX, $l_f_CurY) Then Return True

	Until $l_f_DistToTarget < $l_f_ArrivalDist Or $l_i_Timeout >= $l_i_MaxTimeout

	Return True
EndFunc

; Check if target corpse is the nearest corpse from given position (squared-distance compare)
Func UAI_IsCorpseNearest($a_i_TargetCorpseID, $a_f_X, $a_f_Y)
	Local $l_f_TargetX = UAI_GetAgentInfoByID($a_i_TargetCorpseID, $GC_UAI_AGENT_X)
	Local $l_f_TargetY = UAI_GetAgentInfoByID($a_i_TargetCorpseID, $GC_UAI_AGENT_Y)
	Local $l_f_TDX = $l_f_TargetX - $a_f_X
	Local $l_f_TDY = $l_f_TargetY - $a_f_Y
	Local $l_f_TargetDistSq = $l_f_TDX * $l_f_TDX + $l_f_TDY * $l_f_TDY

	For $i = 1 To $g_i_AgentCacheCount
		Local $l_i_AgentID = UAI_GetAgentInfo($i, $GC_UAI_AGENT_ID)
		If Not UAI_Filter_IsDeadEnemy($l_i_AgentID) Then ContinueLoop
		If $l_i_AgentID = $a_i_TargetCorpseID Then ContinueLoop

		Local $l_f_OtherX = UAI_GetAgentInfo($i, $GC_UAI_AGENT_X)
		Local $l_f_OtherY = UAI_GetAgentInfo($i, $GC_UAI_AGENT_Y)
		Local $l_f_ODX = $l_f_OtherX - $a_f_X
		Local $l_f_ODY = $l_f_OtherY - $a_f_Y

		If ($l_f_ODX * $l_f_ODX + $l_f_ODY * $l_f_ODY) < $l_f_TargetDistSq Then Return False
	Next

	Return True
EndFunc
#EndRegion