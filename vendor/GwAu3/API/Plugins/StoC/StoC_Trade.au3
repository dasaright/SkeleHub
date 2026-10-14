#include-once

; Player trade seen from the server messages (Trade\Cli\TrdCliSess.cpp). Memory only holds the
; player's own trade flags: an EMPTY partner offer, the partner's acceptance and the reason a
; session ended leave no trace there. These messages carry them.
;
; StoC_Poll drains the ring for every reader: keep a single bus reader while a trade is watched.
; Message ids and the "already trading" string key come from build 2026-09-01.

Global Const $GC_I_STOC_TRADE_REQUEST = 0x000          ; (partner) the partner invites us
Global Const $GC_I_STOC_TRADE_ACK = 0x001              ; (result) see $GC_I_STOC_TRADE_ACK_*
Global Const $GC_I_STOC_TRADE_STATUS = 0x002           ; (0, item count) partner composing
Global Const $GC_I_STOC_TRADE_FINALIZE_REVIEW = 0x003  ; (gold) partner submitted, closes the offer
Global Const $GC_I_STOC_TRADE_ITEM_REVIEW = 0x004      ; (item, quantity) one partner item, before 0x003
Global Const $GC_I_STOC_TRADE_PARTNER_ACCEPTED = 0x005 ; (partner) the partner took our invitation
Global Const $GC_I_STOC_TRADE_PARTNER_CONFIRMED = 0x006
Global Const $GC_I_STOC_TRADE_PARTNER_REVOKED_CONFIRM = 0x007
Global Const $GC_I_STOC_TRADE_PARTNER_REVOKED_SUBMIT = 0x008
Global Const $GC_I_STOC_TRADE_EXECUTE = 0x009
Global Const $GC_I_STOC_CHAT_DATA = 0x05D              ; encoded string, first wchar = string key

Global Const $GC_I_STOC_TRADE_ACK_OK = 0         ; our operation acknowledged
Global Const $GC_I_STOC_TRADE_ACK_CANCELLED = 2  ; session cancelled, by us or by the partner
Global Const $GC_I_STOC_TRADE_ACK_EXECUTED = 3   ; trade done, 0x009 follows
Global Const $GC_I_STOC_KEY_ALREADY_TRADING = 0x0ADE ; "<name> is already trading with someone else."

Global Const $GC_AI_STOC_TRADE_IDS[10] = [0x000, 0x001, 0x002, 0x003, 0x004, 0x005, 0x006, 0x007, 0x008, 0x009]

Global Enum _
    $GC_I_STOC_TRADE_SUBMITTED, _
    $GC_I_STOC_TRADE_GOLD, _
    $GC_I_STOC_TRADE_ITEMS, _
    $GC_I_STOC_TRADE_COMPOSING, _
    $GC_I_STOC_TRADE_CONFIRMED, _
    $GC_I_STOC_TRADE_BUSY, _
    $GC_I_STOC_TRADE_RESULT, _
    $GC_I_STOC_TRADE_LAST_ACK, _
    $GC_I_STOC_TRADE_STATE_SIZE

Global $g_av_StoCTrade[$GC_I_STOC_TRADE_STATE_SIZE]
Global $g_b_StoCTradeBusyWatched = False

;~ Description: Start watching trades from a clean state. False if the bus cannot be armed.
; $a_b_WatchBusy also listens to server chat, for PartnerBusy: only while inviting. Chat can fill
; the 64-message ring in a busy outpost, and a full ring drops the trade messages that follow.
Func StoC_WatchTrade($a_b_WatchBusy = False)
	For $l_i_Idx = 0 To UBound($GC_AI_STOC_TRADE_IDS) - 1
		If Not StoC_Subscribe($GC_AI_STOC_TRADE_IDS[$l_i_Idx]) Then Return SetError(1, 0, False)
	Next
	$g_b_StoCTradeBusyWatched = $a_b_WatchBusy
	If $a_b_WatchBusy Then StoC_Subscribe($GC_I_STOC_CHAT_DATA)
	StoC_Poll()
	_StoC_ResetTrade()
	$g_av_StoCTrade[$GC_I_STOC_TRADE_LAST_ACK] = -1
	Return SetError(0, 0, True)
EndFunc   ;==>StoC_WatchTrade

;~ Description: Stop watching trades.
Func StoC_UnwatchTrade()
	For $l_i_Idx = 0 To UBound($GC_AI_STOC_TRADE_IDS) - 1
		StoC_Unsubscribe($GC_AI_STOC_TRADE_IDS[$l_i_Idx])
	Next
	If $g_b_StoCTradeBusyWatched Then StoC_Unsubscribe($GC_I_STOC_CHAT_DATA)
	$g_b_StoCTradeBusyWatched = False
EndFunc   ;==>StoC_UnwatchTrade

;~ Description: Apply the messages received since the last call. Call it in every wait loop.
Func StoC_UpdateTrade()
	Local $l_av_Events = StoC_Poll()
	For $l_i_Idx = 0 To UBound($l_av_Events) - 1
		Switch $l_av_Events[$l_i_Idx][0]
			Case $GC_I_STOC_TRADE_REQUEST, $GC_I_STOC_TRADE_PARTNER_ACCEPTED
				_StoC_ResetTrade()
			Case $GC_I_STOC_TRADE_STATUS
				$g_av_StoCTrade[$GC_I_STOC_TRADE_COMPOSING] = $l_av_Events[$l_i_Idx][2]
			Case $GC_I_STOC_TRADE_ITEM_REVIEW
				$g_av_StoCTrade[$GC_I_STOC_TRADE_ITEMS] += 1
			Case $GC_I_STOC_TRADE_FINALIZE_REVIEW
				$g_av_StoCTrade[$GC_I_STOC_TRADE_SUBMITTED] = True
				$g_av_StoCTrade[$GC_I_STOC_TRADE_GOLD] = $l_av_Events[$l_i_Idx][1]
			Case $GC_I_STOC_TRADE_PARTNER_REVOKED_SUBMIT
				$g_av_StoCTrade[$GC_I_STOC_TRADE_SUBMITTED] = False
				$g_av_StoCTrade[$GC_I_STOC_TRADE_GOLD] = 0
				$g_av_StoCTrade[$GC_I_STOC_TRADE_ITEMS] = 0
				$g_av_StoCTrade[$GC_I_STOC_TRADE_CONFIRMED] = False
			Case $GC_I_STOC_TRADE_PARTNER_CONFIRMED
				$g_av_StoCTrade[$GC_I_STOC_TRADE_CONFIRMED] = True
			Case $GC_I_STOC_TRADE_PARTNER_REVOKED_CONFIRM
				$g_av_StoCTrade[$GC_I_STOC_TRADE_CONFIRMED] = False
			Case $GC_I_STOC_TRADE_ACK
				$g_av_StoCTrade[$GC_I_STOC_TRADE_LAST_ACK] = $l_av_Events[$l_i_Idx][1]
				If $l_av_Events[$l_i_Idx][1] = $GC_I_STOC_TRADE_ACK_CANCELLED Or _
					$l_av_Events[$l_i_Idx][1] = $GC_I_STOC_TRADE_ACK_EXECUTED Then _
					$g_av_StoCTrade[$GC_I_STOC_TRADE_RESULT] = $l_av_Events[$l_i_Idx][1]
			Case $GC_I_STOC_TRADE_EXECUTE
				$g_av_StoCTrade[$GC_I_STOC_TRADE_RESULT] = $GC_I_STOC_TRADE_ACK_EXECUTED
			Case $GC_I_STOC_CHAT_DATA
				If BitAND($l_av_Events[$l_i_Idx][1], 0xFFFF) = $GC_I_STOC_KEY_ALREADY_TRADING Then _
					$g_av_StoCTrade[$GC_I_STOC_TRADE_BUSY] = True
		EndSwitch
	Next
EndFunc   ;==>StoC_UpdateTrade

;~ Description: Watched trade state, as of the last StoC_UpdateTrade. 0 for an unknown key.
; PartnerSubmitted  True once the partner submitted, EMPTY offer included.
; PartnerGold       gold of the submitted offer.
; PartnerItems      items of the submitted offer.
; PartnerComposing  items the partner has placed, submitted or not.
; PartnerConfirmed  True while the partner has accepted. Only sent if he accepts before us: if
;                   he accepts after, the server executes at once and Result says so.
; PartnerBusy       True after "already trading with someone else" (1.3 to 1.9 s after inviting),
;                   when watched with $a_b_WatchBusy.
; Result            0 open, $GC_I_STOC_TRADE_ACK_CANCELLED or $GC_I_STOC_TRADE_ACK_EXECUTED.
; LastAck           result of the last acknowledged operation, -1 before any.
Func StoC_GetTradeInfo($a_s_Info = "")
	Switch $a_s_Info
		Case "PartnerSubmitted"
			Return $g_av_StoCTrade[$GC_I_STOC_TRADE_SUBMITTED]
		Case "PartnerGold"
			Return $g_av_StoCTrade[$GC_I_STOC_TRADE_GOLD]
		Case "PartnerItems"
			Return $g_av_StoCTrade[$GC_I_STOC_TRADE_ITEMS]
		Case "PartnerComposing"
			Return $g_av_StoCTrade[$GC_I_STOC_TRADE_COMPOSING]
		Case "PartnerConfirmed"
			Return $g_av_StoCTrade[$GC_I_STOC_TRADE_CONFIRMED]
		Case "PartnerBusy"
			Return $g_av_StoCTrade[$GC_I_STOC_TRADE_BUSY]
		Case "Result"
			Return $g_av_StoCTrade[$GC_I_STOC_TRADE_RESULT]
		Case "LastAck"
			Return $g_av_StoCTrade[$GC_I_STOC_TRADE_LAST_ACK]
	EndSwitch
	Return 0
EndFunc   ;==>StoC_GetTradeInfo

;~ Description: New session, or a new watch: forget the previous partner and outcome.
Func _StoC_ResetTrade()
	$g_av_StoCTrade[$GC_I_STOC_TRADE_SUBMITTED] = False
	$g_av_StoCTrade[$GC_I_STOC_TRADE_GOLD] = 0
	$g_av_StoCTrade[$GC_I_STOC_TRADE_ITEMS] = 0
	$g_av_StoCTrade[$GC_I_STOC_TRADE_COMPOSING] = 0
	$g_av_StoCTrade[$GC_I_STOC_TRADE_CONFIRMED] = False
	$g_av_StoCTrade[$GC_I_STOC_TRADE_BUSY] = False
	$g_av_StoCTrade[$GC_I_STOC_TRADE_RESULT] = 0
EndFunc   ;==>_StoC_ResetTrade
