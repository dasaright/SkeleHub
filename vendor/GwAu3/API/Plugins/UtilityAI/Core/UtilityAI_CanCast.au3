#include-once

;Check if auto attack can be made
Func UAI_CanAutoAttack()
	If Not UAI_GetPlayerInfo($GC_UAI_AGENT_IsHexed) Then Return True

	;~ Specific hex checks
	If UAI_PlayerHasEffect($GC_I_SKILL_ID_SPIRIT_SHACKLES) Then Return False

	If UAI_PlayerHasEffect($GC_I_SKILL_ID_INEPTITUDE) Then Return False
	If UAI_PlayerHasEffect($GC_I_SKILL_ID_CLUMSINESS) Then Return False
	If UAI_PlayerHasEffect($GC_I_SKILL_ID_WANDERING_EYE) Then Return False

	; Check for hexes that punish attacking
	Local $l_i_IncomingDamage = 0
	If UAI_PlayerHasEffect($GC_I_SKILL_ID_EMPATHY) Then $l_i_IncomingDamage += UAI_GetPlayerEffectInfo($GC_I_SKILL_ID_EMPATHY, $GC_UAI_EFFECT_Scale)
	If UAI_PlayerHasEffect($GC_I_SKILL_ID_SPITEFUL_SPIRIT) Then $l_i_IncomingDamage += UAI_GetPlayerEffectInfo($GC_I_SKILL_ID_SPITEFUL_SPIRIT, $GC_UAI_EFFECT_Scale)
	If UAI_PlayerHasEffect($GC_I_SKILL_ID_SPOIL_VICTOR) Then $l_i_IncomingDamage += UAI_GetPlayerEffectInfo($GC_I_SKILL_ID_SPOIL_VICTOR, $GC_UAI_EFFECT_Scale)

	Return Not ($l_i_IncomingDamage > (UAI_GetPlayerInfo($GC_UAI_AGENT_CurrentHP) + UAI_GetPlayerInfo($GC_UAI_AGENT_MaxHP * 0.15)))
EndFunc

; Check if I have resource to use the skill
Func UAI_CanUse($a_i_SkillSlot)
	;~ EARLY CHECK IF CAST IS SENSIBLE AT ALL
	If Not UAI_IsCastSensible($a_i_SkillSlot) Then Return False

	;~ ADRENALINE
	If UAI_GetStaticSkillInfo($a_i_SkillSlot, $GC_UAI_STATIC_SKILL_Adrenaline) <> 0 Then
		If UAI_GetDynamicSkillInfo($a_i_SkillSlot, $GC_UAI_DYNAMIC_SKILL_Adrenaline) < UAI_GetStaticSkillInfo($a_i_SkillSlot, $GC_UAI_STATIC_SKILL_Adrenaline) Then Return False
		Return True
	EndIf

	;~ COOLDOWN
	If Not UAI_GetDynamicSkillInfo($a_i_SkillSlot, $GC_UAI_DYNAMIC_SKILL_IsRecharged) Then Return False

	;~ HEALTH COST (Sacrifice spells + Masochism effect on ALL spells)
	Local $l_i_TotalHealthCost = 0

	; Check base sacrifice cost (for sacrifice spells)
	Local $l_i_BaseSacrificeCost = Skill_GetSkillInfo(UAI_GetStaticSkillInfo($a_i_SkillSlot, $GC_UAI_STATIC_SKILL_SkillID), "HealthCost")
	If $l_i_BaseSacrificeCost <> 0 Then
		$l_i_TotalHealthCost = UAI_GetPlayerInfo($GC_UAI_AGENT_MaxHP) * $l_i_BaseSacrificeCost / 100

		; Check effects that modify sacrifice cost
		If UAI_PlayerHasEffect($GC_I_SKILL_ID_Awaken_the_Blood) Then $l_i_TotalHealthCost = $l_i_TotalHealthCost + ($l_i_TotalHealthCost * 0.5) ; +50% cost
		If UAI_PlayerHasEffect($GC_I_SKILL_ID_Scourge_Sacrifice) Then $l_i_TotalHealthCost = $l_i_TotalHealthCost * 2 ; Double cost
	EndIf

	; Masochism: Sacrifice 5% of max HP when casting ANY spell
	If UAI_PlayerHasEffect($GC_I_SKILL_ID_Masochism) Then $l_i_TotalHealthCost = $l_i_TotalHealthCost + (UAI_GetPlayerInfo($GC_UAI_AGENT_MaxHP) * 0.05)

	; Check if we have enough HP for the total health cost
	If $l_i_TotalHealthCost > 0 And UAI_GetPlayerInfo($GC_UAI_AGENT_CurrentHP) <= $l_i_TotalHealthCost Then Return False

	;~ OVERCAST
	Local $l_i_OvercastCost = Skill_GetSkillInfo(UAI_GetStaticSkillInfo($a_i_SkillSlot, $GC_UAI_STATIC_SKILL_SkillID), "Overcast")
	If $l_i_OvercastCost <> 0 Then
		Local $l_i_CurrentOvercast = UAI_GetPlayerInfo($GC_UAI_AGENT_Overcast)
		Local $l_i_MaxEnergy = UAI_GetPlayerInfo($GC_UAI_AGENT_MaxEnergy)
		If UAI_PlayerHasEffect($GC_I_SKILL_ID_Glyph_of_Energy) Then $l_i_OvercastCost = 0
		If ($l_i_CurrentOvercast + $l_i_OvercastCost) >= ($l_i_MaxEnergy * 0.5) Then Return False
	EndIf

	;~ ENERGY
	Local $l_i_BaseEnergyCost = UAI_GetStaticSkillInfo($a_i_SkillSlot, $GC_UAI_STATIC_SKILL_EnergyCost)
	Local $l_i_EnergyCost = $l_i_BaseEnergyCost
	Local $l_i_CurrentEnergy  = UAI_GetPlayerInfo($GC_UAI_AGENT_CurrentEnergy)

	; Single-valued skill properties the modifiers are gated on (read once)
	Local $l_i_SkillType = UAI_GetStaticSkillInfo($a_i_SkillSlot, $GC_UAI_STATIC_SKILL_SkillType)
	Local $l_i_Attribute = UAI_GetStaticSkillInfo($a_i_SkillSlot, $GC_UAI_STATIC_SKILL_Attribute)
	Local $l_i_Target = UAI_GetStaticSkillInfo($a_i_SkillSlot, $GC_UAI_STATIC_SKILL_Target)
	Local $l_i_WeaponReq = UAI_GetStaticSkillInfo($a_i_SkillSlot, $GC_UAI_STATIC_SKILL_WeaponReq)
	Local $l_i_Combo = UAI_GetStaticSkillInfo($a_i_SkillSlot, $GC_UAI_STATIC_SKILL_Combo)
	Local $l_b_WotEP = False

	; Ungated multiplicative increase (applies to all skills)
	If UAI_PlayerHasEffect($GC_I_SKILL_ID_Quickening_Zephyr) Then $l_i_EnergyCost *= 1.3 ; +30%

	; Type-gated increases AND reductions: only the skill's one type runs
	Switch $l_i_SkillType
		Case $GC_I_SKILL_TYPE_HEX
			If UAI_PlayerHasEffect($GC_I_SKILL_ID_Natures_Renewal) Then $l_i_EnergyCost *= 2 ; double cost
			If UAI_PlayerHasEffect($GC_I_SKILL_ID_Anguished_Was_Lingwah) And _
				($l_i_Attribute = $GC_I_ATTRIBUTE_COMMUNING Or _
				$l_i_Attribute = $GC_I_ATTRIBUTE_RESTORATION_MAGIC Or _
				$l_i_Attribute = $GC_I_ATTRIBUTE_CHANNELING_MAGIC Or _
				$l_i_Attribute = $GC_I_ATTRIBUTE_SPAWNING_POWER) Then _
				$l_i_EnergyCost -= 5 ; Ritualist hexes -5

		Case $GC_I_SKILL_TYPE_ENCHANTMENT
			If UAI_PlayerHasEffect($GC_I_SKILL_ID_Natures_Renewal) Then $l_i_EnergyCost *= 2 ; double cost
			;~ If UAI_AgentHasEffect($GC_I_SKILL_ID_Air_of_Enchantment) Then $l_i_EnergyCost -= 10 ; Target not set at this stage

		Case $GC_I_SKILL_TYPE_SIGNET
			If UAI_PlayerHasEffect($GC_I_SKILL_ID_Primal_Echoes) Then $l_i_EnergyCost += 10 ; signets +10

		Case $GC_I_SKILL_TYPE_CHANT, $GC_I_SKILL_TYPE_SHOUT
			If UAI_PlayerHasEffect($GC_I_SKILL_ID_Roaring_Winds) Then _
				$l_i_EnergyCost += UAI_GetPlayerEffectInfo($GC_I_SKILL_ID_Roaring_Winds, $GC_UAI_EFFECT_Scale) ; +scaled energy

		Case $GC_I_SKILL_TYPE_SPELL
			If $l_i_Target <> $GC_I_SKILL_TARGET_SELF And (UAI_PlayerHasEffect($GC_I_SKILL_ID_SELFLESS_SPIRIT_LUXON) Or UAI_PlayerHasEffect($GC_I_SKILL_ID_SELFLESS_SPIRIT_KURZICK)) Then _
				$l_i_EnergyCost -= 3 ; spells on allies -3
			If UAI_PlayerHasEffect($GC_I_SKILL_ID_Glyph_of_Lesser_Energy) Then 
				$l_i_EnergyCost -= UAI_GetPlayerEffectInfo($GC_I_SKILL_ID_Glyph_of_Lesser_Energy, $GC_UAI_EFFECT_Scale)
			ElseIf UAI_PlayerHasEffect($GC_I_SKILL_ID_Glyph_of_Energy) Then
				$l_i_EnergyCost -= UAI_GetPlayerEffectInfo($GC_I_SKILL_ID_Glyph_of_Energy, $GC_UAI_EFFECT_Scale)
			EndIf
			If UAI_PlayerHasEffect($GC_I_SKILL_ID_Attuned_Was_Songkai) Then _
				$l_i_EnergyCost -= ($l_i_BaseEnergyCost * UAI_GetPlayerEffectInfo($GC_I_SKILL_ID_Attuned_Was_Songkai, $GC_UAI_EFFECT_Scale)) ; -scaled base energy

		Case $GC_I_SKILL_TYPE_RITUAL
			If UAI_PlayerHasEffect($GC_I_SKILL_ID_Attuned_Was_Songkai) Then _
				$l_i_EnergyCost -= ($l_i_BaseEnergyCost * UAI_GetPlayerEffectInfo($GC_I_SKILL_ID_Attuned_Was_Songkai, $GC_UAI_EFFECT_Scale)) ; -scaled base energy
			If UAI_PlayerHasEffect($GC_I_SKILL_ID_Soul_Twisting) Then $l_i_EnergyCost -= 15 ; binding rituals -15

		Case $GC_I_SKILL_TYPE_WEAPON_SPELL, $GC_I_SKILL_TYPE_ITEM_SPELL
			If UAI_PlayerHasEffect($GC_I_SKILL_ID_Renewing_Memories) Then _
				$l_i_EnergyCost -= ($l_i_BaseEnergyCost * UAI_GetPlayerEffectInfo($GC_I_SKILL_ID_Renewing_Memories, $GC_UAI_EFFECT_Scale)) ; -scaled base energy
	EndSwitch

	If UAI_PlayerHasEffect($GC_I_SKILL_ID_Energizing_Wind) Then $l_i_EnergyCost -= 15 ; -15

	; Attribute-gated reductions
	Switch $l_i_Attribute
		Case $GC_I_ATTRIBUTE_HEALING_PRAYERS
			If UAI_PlayerHasEffect($GC_I_SKILL_ID_Divine_Spirit) Then $l_i_EnergyCost -= 5 ; Monk spells -5
			If UAI_PlayerHasEffect($GC_I_SKILL_ID_Healers_Covenant) Then $l_i_EnergyCost -= 3 ; Healing Prayers -3

		Case $GC_I_ATTRIBUTE_SMITING_PRAYERS, $GC_I_ATTRIBUTE_PROTECTION_PRAYERS, $GC_I_ATTRIBUTE_DIVINE_FAVOR
			If UAI_PlayerHasEffect($GC_I_SKILL_ID_Divine_Spirit) Then $l_i_EnergyCost -= 5 ; Monk spells -5

		Case $GC_I_ATTRIBUTE_BLOOD_MAGIC To $GC_I_ATTRIBUTE_SOUL_REAPING
			If UAI_PlayerHasEffect($GC_I_SKILL_ID_Cultists_Fervor) Then _
				$l_i_EnergyCost -= UAI_GetPlayerEffectInfo($GC_I_SKILL_ID_Cultists_Fervor, $GC_UAI_EFFECT_Scale) ; Necro spells -scaled energy
	EndSwitch

	; Single-property gates (weapon / combo)
	If $l_i_WeaponReq = $GC_I_WEAPON_TYPE_BOW And UAI_PlayerHasEffect($GC_I_SKILL_ID_Expert_Focus) Then _
		$l_i_EnergyCost -= 2 ; bow attacks -2

	If ($l_i_Combo = $GC_I_SKILL_COMBO_OFF_HAND_ATTACK Or $l_i_Combo = $GC_I_SKILL_COMBO_DUAL_ATTACK) Then
		$l_b_WotEP = UAI_PlayerHasEffect($GC_I_SKILL_ID_Way_of_the_Empty_Palm)
		If $l_b_WotEP Then $l_i_EnergyCost = 0 ; off-hand / dual attacks cost 0
	EndIf

	; Clamp: minimum cost 1 (0 only under Way of the Empty Palm)
	If $l_i_EnergyCost < 1 And Not $l_b_WotEP Then $l_i_EnergyCost = 1
	If $l_i_EnergyCost < 0 Then $l_i_EnergyCost = 0

	If $l_i_CurrentEnergy < Ceiling($l_i_EnergyCost) Then Return False

	Return True
EndFunc

Func UAI_CanDrop($a_i_SkillSlot)
	Switch UAI_GetStaticSkillInfo($a_i_SkillSlot, $GC_UAI_STATIC_SKILL_SkillID)
		Case $GC_I_SKILL_ID_ANGUISHED_WAS_LINGWAH
			; Drop if all Ritualist hexes in skillbar are recharging
			Local $l_b_HasRitualistHex = False
			For $i = 1 To 8
				If $i = $a_i_SkillSlot Then ContinueLoop ; Skip the item spell itself
				Local $l_i_SkillType = UAI_GetStaticSkillInfo($i, $GC_UAI_STATIC_SKILL_SkillType)
				Local $l_i_Profession = UAI_GetStaticSkillInfo($i, $GC_UAI_STATIC_SKILL_Profession)
				If $l_i_SkillType = $GC_I_SKILL_TYPE_HEX And $l_i_Profession = $GC_I_PROFESSION_RITUALIST Then
					$l_b_HasRitualistHex = True
					If UAI_GetDynamicSkillInfo($i, $GC_UAI_DYNAMIC_SKILL_IsRecharged) Then Return False
				EndIf
			Next
			Return $l_b_HasRitualistHex
		Case $GC_I_SKILL_ID_BLIND_WAS_MINGSON
			; Drop if physical attackers (melee/ranged, not casters) in nearby range
			If UAI_CountAgents(-2, $GC_I_RANGE_NEARBY, "UAI_Filter_IsLivingEnemy|UAI_Filter_IsNotCaster") >= 2 Then Return True

			; Otherwise, check if physical attackers in larger range - move to them
			Local $l_av_BestPos = UAI_GetBestMartialEnemyPosition($GC_I_RANGE_NEARBY)
			If $l_av_BestPos[2] <= 1 Then Return False ; No physical enemies

			; Move to physical enemy cluster
			Local $l_f_TargetX = $l_av_BestPos[0]
			Local $l_f_TargetY = $l_av_BestPos[1]
			Local $l_i_Timeout = 0

			Do
				Map_Move($l_f_TargetX, $l_f_TargetY, 0)
				Sleep(32)
				$l_i_Timeout += 32

				If UAI_CountAgents(-2, $GC_I_RANGE_NEARBY, "UAI_Filter_IsLivingEnemy|UAI_Filter_IsNotCaster") >= 2 Then Return True

				Local $l_f_CurX = Agent_GetAgentInfo(-2, "X")
				Local $l_f_CurY = Agent_GetAgentInfo(-2, "Y")
				Local $l_f_DiffX = $l_f_TargetX - $l_f_CurX
				Local $l_f_DiffY = $l_f_TargetY - $l_f_CurY
				Local $l_f_DistToTarget = Sqrt($l_f_DiffX * $l_f_DiffX + $l_f_DiffY * $l_f_DiffY)

				If $l_f_DistToTarget < 80 Then Return True

			Until $l_i_Timeout >= 3000
			Return UAI_CountAgents(-2, $GC_I_RANGE_NEARBY, "UAI_Filter_IsLivingEnemy|UAI_Filter_IsNotCaster") >= 1
		Case $GC_I_SKILL_ID_CRUEL_WAS_DAOSHEN
			; Drop: lightning damage to all nearby foes
			If UAI_CountAgents(-2, $GC_I_RANGE_NEARBY, "UAI_Filter_IsLivingEnemy") >= 2 Then Return True

			Local $l_av_BestPos = UAI_GetBestOffensiveWardPosition($GC_I_RANGE_NEARBY)
			If $l_av_BestPos[2] <= 1 Then Return False

			Local $l_f_TargetX = $l_av_BestPos[0]
			Local $l_f_TargetY = $l_av_BestPos[1]
			Local $l_i_Timeout = 0

			Do
				Map_Move($l_f_TargetX, $l_f_TargetY, 0)
				Sleep(32)
				$l_i_Timeout += 32
				If UAI_CountAgents(-2, $GC_I_RANGE_NEARBY, "UAI_Filter_IsLivingEnemy") >= 2 Then Return True
				Local $l_f_CurX = Agent_GetAgentInfo(-2, "X")
				Local $l_f_CurY = Agent_GetAgentInfo(-2, "Y")
				Local $l_f_DistToTarget = Sqrt(($l_f_TargetX - $l_f_CurX)^2 + ($l_f_TargetY - $l_f_CurY)^2)
				If $l_f_DistToTarget < 80 Then Return True
			Until $l_i_Timeout >= 3000

			Return UAI_CountAgents(-2, $GC_I_RANGE_NEARBY, "UAI_Filter_IsLivingEnemy") >= 1

		Case $GC_I_SKILL_ID_DESTRUCTIVE_WAS_GLAIVE
			; Drop: lightning damage to all foes in AREA (larger range than nearby)
			If UAI_CountAgents(-2, $GC_I_RANGE_AREA, "UAI_Filter_IsLivingEnemy") >= 2 Then Return True

			Local $l_av_BestPos = UAI_GetBestOffensiveWardPosition($GC_I_RANGE_AREA)
			If $l_av_BestPos[2] <= 1 Then Return False

			Local $l_f_TargetX = $l_av_BestPos[0]
			Local $l_f_TargetY = $l_av_BestPos[1]
			Local $l_i_Timeout = 0

			Do
				Map_Move($l_f_TargetX, $l_f_TargetY, 0)
				Sleep(32)
				$l_i_Timeout += 32
				If UAI_CountAgents(-2, $GC_I_RANGE_AREA, "UAI_Filter_IsLivingEnemy") >= 2 Then Return True
				Local $l_f_CurX = Agent_GetAgentInfo(-2, "X")
				Local $l_f_CurY = Agent_GetAgentInfo(-2, "Y")
				Local $l_f_DistToTarget = Sqrt(($l_f_TargetX - $l_f_CurX)^2 + ($l_f_TargetY - $l_f_CurY)^2)
				If $l_f_DistToTarget < 80 Then Return True
			Until $l_i_Timeout >= 3000

			Return UAI_CountAgents(-2, $GC_I_RANGE_AREA, "UAI_Filter_IsLivingEnemy") >= 1

		Case $GC_I_SKILL_ID_GRASPING_WAS_KUURONG
			; Drop: damage + knockdown to all nearby foes
			If UAI_CountAgents(-2, $GC_I_RANGE_NEARBY, "UAI_Filter_IsLivingEnemy") >= 2 Then Return True

			Local $l_av_BestPos = UAI_GetBestOffensiveWardPosition($GC_I_RANGE_NEARBY)
			If $l_av_BestPos[2] <= 1 Then Return False

			Local $l_f_TargetX = $l_av_BestPos[0]
			Local $l_f_TargetY = $l_av_BestPos[1]
			Local $l_i_Timeout = 0

			Do
				Map_Move($l_f_TargetX, $l_f_TargetY, 0)
				Sleep(32)
				$l_i_Timeout += 32
				If UAI_CountAgents(-2, $GC_I_RANGE_NEARBY, "UAI_Filter_IsLivingEnemy") >= 2 Then Return True
				Local $l_f_CurX = Agent_GetAgentInfo(-2, "X")
				Local $l_f_CurY = Agent_GetAgentInfo(-2, "Y")
				Local $l_f_DistToTarget = Sqrt(($l_f_TargetX - $l_f_CurX)^2 + ($l_f_TargetY - $l_f_CurY)^2)
				If $l_f_DistToTarget < 80 Then Return True
			Until $l_i_Timeout >= 3000

			Return UAI_CountAgents(-2, $GC_I_RANGE_NEARBY, "UAI_Filter_IsLivingEnemy") >= 1
		Case $GC_I_SKILL_ID_DEFIANT_WAS_XINRAE
			; Drop: damage + knockdown to all nearby foes
			If UAI_CountAgents(-2, $GC_I_RANGE_NEARBY, "UAI_Filter_IsLivingEnemy") >= 2 Then Return True

			Local $l_av_BestPos = UAI_GetBestOffensiveWardPosition($GC_I_RANGE_NEARBY)
			If $l_av_BestPos[2] <= 1 Then Return False

			Local $l_f_TargetX = $l_av_BestPos[0]
			Local $l_f_TargetY = $l_av_BestPos[1]
			Local $l_i_Timeout = 0

			Do
				Map_Move($l_f_TargetX, $l_f_TargetY, 0)
				Sleep(32)
				$l_i_Timeout += 32
				If UAI_CountAgents(-2, $GC_I_RANGE_NEARBY, "UAI_Filter_IsLivingEnemy") >= 2 Then Return True
				Local $l_f_CurX = Agent_GetAgentInfo(-2, "X")
				Local $l_f_CurY = Agent_GetAgentInfo(-2, "Y")
				Local $l_f_DistToTarget = Sqrt(($l_f_TargetX - $l_f_CurX)^2 + ($l_f_TargetY - $l_f_CurY)^2)
				If $l_f_DistToTarget < 80 Then Return True
			Until $l_i_Timeout >= 3000

			Return UAI_CountAgents(-2, $GC_I_RANGE_NEARBY, "UAI_Filter_IsLivingEnemy") >= 1
		Case $GC_I_SKILL_ID_ENERGETIC_WAS_LEE_SA
			; Drop to gain energy when running low
			Local $l_i_CurrentEnergy = UAI_GetPlayerInfo($GC_UAI_AGENT_CurrentEnergy)
			Local $l_i_MaxEnergy = UAI_GetPlayerInfo($GC_UAI_AGENT_MaxEnergy)

			; Drop if energy is below 25% or below 10 energy
			If $l_i_CurrentEnergy < ($l_i_MaxEnergy * 0.25) Or $l_i_CurrentEnergy < 15 Then Return True
			Return False
		Case $GC_I_SKILL_ID_GENEROUS_WAS_TSUNGRAI
			; Drop to heal when health is low
			Local $l_i_CurrentHP = UAI_GetPlayerInfo($GC_UAI_AGENT_CurrentHP)
			Local $l_i_MaxHP = UAI_GetPlayerInfo($GC_UAI_AGENT_MaxHP)

			; Drop if health is below 50%
			If $l_i_CurrentHP < ($l_i_MaxHP * 0.50) Then Return True
			Return False
		Case $GC_I_SKILL_ID_LIVELY_WAS_NAOMEI
			; Drop to resurrect dead party members in area
			If UAI_CountAgents(-2, $GC_I_RANGE_AREA, "UAI_Filter_IsDeadAlly") >= 1 Then Return True

			; Otherwise, check if dead allies in larger range - move to them
			Local $l_i_DeadAlly = UAI_GetNearestAgent(-2, 1200, "UAI_Filter_IsDeadAlly")
			If $l_i_DeadAlly = 0 Then Return False ; No dead allies

			; Move toward dead ally
			Local $l_f_TargetX = UAI_GetAgentInfoByID($l_i_DeadAlly, $GC_UAI_AGENT_X)
			Local $l_f_TargetY = UAI_GetAgentInfoByID($l_i_DeadAlly, $GC_UAI_AGENT_Y)
			Local $l_i_Timeout = 0

			Do
				Map_Move($l_f_TargetX, $l_f_TargetY, 0)
				Sleep(32)
				$l_i_Timeout += 32

				If UAI_CountAgents(-2, $GC_I_RANGE_AREA, "UAI_Filter_IsDeadAlly") >= 1 Then Return True

				Local $l_f_CurX = Agent_GetAgentInfo(-2, "X")
				Local $l_f_CurY = Agent_GetAgentInfo(-2, "Y")
				Local $l_f_DiffX = $l_f_TargetX - $l_f_CurX
				Local $l_f_DiffY = $l_f_TargetY - $l_f_CurY
				Local $l_f_DistToTarget = Sqrt($l_f_DiffX * $l_f_DiffX + $l_f_DiffY * $l_f_DiffY)

				If $l_f_DistToTarget < 80 Then Return True

			Until $l_i_Timeout >= 3000

			Return UAI_CountAgents(-2, $GC_I_RANGE_AREA, "UAI_Filter_IsDeadAlly") >= 1
		Case $GC_I_SKILL_ID_PROTECTIVE_WAS_KAOLAI
			; Drop to heal all party members when multiple allies need healing
			Local $l_i_InjuredAllies = 0

			For $i = 1 To $g_i_AgentCacheCount
				Local $l_i_AgentID = UAI_GetAgentInfo($i, $GC_UAI_AGENT_ID)
				If Not UAI_Filter_IsLivingAlly($l_i_AgentID) Then ContinueLoop
				If UAI_GetAgentInfo($i, $GC_UAI_AGENT_HP) < 0.75 Then
					$l_i_InjuredAllies += 1
				EndIf
			Next

			; Also check if player is below 70%
			Local $l_i_CurrentHP = UAI_GetPlayerInfo($GC_UAI_AGENT_CurrentHP)
			Local $l_i_MaxHP = UAI_GetPlayerInfo($GC_UAI_AGENT_MaxHP)
			Local $l_b_PlayerLow = ($l_i_CurrentHP < ($l_i_MaxHP * 0.70))

			; Drop if 2+ allies below 70% OR player is below 70%
			If $l_i_InjuredAllies >= 2 Or $l_b_PlayerLow Then Return True
			Return False
		Case $GC_I_SKILL_ID_PURE_WAS_LI_MING
			; Drop to remove conditions from allies in earshot
			Return UAI_CountAgents(-2, $GC_I_RANGE_EARSHOT, "UAI_Filter_IsLivingAlly|UAI_Filter_IsConditioned") >= 2
		Case $GC_I_SKILL_ID_RESILIENT_WAS_XIKO
			; Drop to remove conditions from self
			Return UAI_GetPlayerInfo($GC_UAI_AGENT_IsConditioned)
		Case $GC_I_SKILL_ID_VOCAL_WAS_SOGOLON, $GC_I_SKILL_ID_ATTUNED_WAS_SONGKAI, $GC_I_SKILL_ID_VENGEFUL_WAS_KHANHEI, _
				$GC_I_SKILL_ID_TRANQUIL_WAS_TANASEN, $GC_I_SKILL_ID_MIGHTY_WAS_VORIZUN
			Return False
	EndSwitch

	Return False
EndFunc

Func UAI_IsCastSensible($a_i_SkillSlot)
    Local $l_i_TargetType = UAI_GetStaticSkillInfo($a_i_SkillSlot, $GC_UAI_STATIC_SKILL_Target)
    If $l_i_TargetType <> $GC_I_SKILL_TARGET_SELF Then Return True

    Local $l_i_SkillType = UAI_GetStaticSkillInfo($a_i_SkillSlot, $GC_UAI_STATIC_SKILL_SkillType)
    Local $l_i_SkillID = UAI_GetStaticSkillInfo($a_i_SkillSlot, $GC_UAI_STATIC_SKILL_SkillID)

    Switch $l_i_SkillType
        Case $GC_I_SKILL_TYPE_ENCHANTMENT, $GC_I_SKILL_TYPE_WARD, $GC_I_SKILL_TYPE_SHOUT, _
        	$GC_I_SKILL_TYPE_RITUAL, $GC_I_SKILL_TYPE_FORM, $GC_I_SKILL_TYPE_ECHO_REFRAIN
			Return _UAI_EffectEndingSoon($l_i_SkillID, $a_i_SkillSlot)
		Case $GC_I_SKILL_TYPE_STANCE
			If Not UAI_PlayerHasEffectType("HasStance") Then Return True
			If @extended <> $l_i_SkillID Then Return False
			Return _UAI_EffectEndingSoon($l_i_SkillID, $a_i_SkillSlot)
		Case $GC_I_SKILL_TYPE_GLYPH
			If Not UAI_PlayerHasEffectType("HasGlyph") Then Return True
			If @extended <> $l_i_SkillID Then Return False
			Return _UAI_EffectEndingSoon($l_i_SkillID, $a_i_SkillSlot)
		Case  $GC_I_SKILL_TYPE_PREPARATION
			If Not UAI_PlayerHasEffectType("HasPreparation") Then Return True
			If @extended <> $l_i_SkillID Then Return False
			Return _UAI_EffectEndingSoon($l_i_SkillID, $a_i_SkillSlot)
    EndSwitch

    Return True
EndFunc

Func _UAI_EffectEndingSoon($a_i_SkillID, $a_i_SkillSlot)
	Return UAI_GetPlayerEffectInfo($a_i_SkillID, $GC_UAI_EFFECT_TimeRemaining) <= _
		(UAI_GetStaticSkillInfo($a_i_SkillSlot, $GC_UAI_STATIC_SKILL_Activation) * 1000 + 1000)
EndFunc