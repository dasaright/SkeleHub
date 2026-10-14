#include-once

;~ Description: Drop a buff with specific skill ID targeting a specific agent
Func Effect_DropBond($a_i_SkillID, $a_i_AgentID = -2, $a_i_TargetID = 0)
    Local $l_i_BondID = Agent_GetAgentBondInfo($a_i_AgentID, $a_i_SkillID, $a_i_TargetID, "BondID")
    If $l_i_BondID = 0 Then Return

    Return Core_SendPacket(0x8, $GC_I_HEADER_BOND_DROP, $l_i_BondID)
EndFunc ;==>DropBuff