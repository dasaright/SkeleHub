#include-once
; #INDEX# =======================================================================================================================
; Title .........: LogMessages.au3
; AutoIt Version : 3.3.16.1
; Language ......: English
; Description ...: API-layer logging: routes every message to a registered callback when one is attached (the
;                  supported path for script frontends), otherwise renders color-coded lines into a RichEdit
;                  control (the API's built-in debug UI). Function names and signatures are FROZEN - API
;                  internals call them.
; ===============================================================================================================================
;
;  EXTERNAL SYMBOLS (provided by the API's constants, pulled in by the API master include; NOT declared here
;  to avoid double-initialization): $GC_I_LOG_MSGTYPE_DEBUG / _INFO / _WARNING / _ERROR / _CRITICAL and
;  $g_b_DebugMode.
;
;  DEBUG GATE: DEBUG-typed messages are dropped BEFORE any dispatch when $g_b_DebugMode is off - the gate
;  applies to the callback path and the RichEdit path alike.
; ===============================================================================================================================

; #GLOBALS - CALLBACK# ==========================================================================================================
Global $g_s_Log_Callback = "" ; registered sink (function NAME string); "" = use the RichEdit path
; ===============================================================================================================================

; #FUNCTION# ====================================================================================================================
; Name...........: Log_SetCallback
; Description ...: Registers the callback that receives every log message as (message, msgType, author). Takes a
;                  function NAME string per AutoIt's dispatch standard (AdlibRegister, GUICtrlSetOnEvent, ...);
;                  "" detaches and falls back to the RichEdit path. The name is validated at registration so a
;                  typo fails HERE instead of silently dropping every future message.
; Syntax.........: Log_SetCallback ( $a_s_Callback )
; Parameters ....: $a_s_Callback - String: function name (e.g. "LogEx_WriteLog"), or "" to detach.
; Return values .: True on success (registered or detached); False with @error = 1 if the name does not resolve
;                  to a function (previous registration kept).
; ===============================================================================================================================
Func Log_SetCallback($a_s_Callback)
    If $a_s_Callback = "" Then
        $g_s_Log_Callback = ""
        Return True
    EndIf

    If Not IsFunc(Execute($a_s_Callback)) Then Return SetError(1, 0, False)

    $g_s_Log_Callback = $a_s_Callback
    Return True
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: Log_Message
; Description ...: Central dispatch: applies the DEBUG gate, then forwards to the registered callback if one is
;                  attached; otherwise appends a color-coded "[time] - [TYPE] - [author] message" line to the
;                  given RichEdit control (wiping it past ~30k chars) and follows the newest line.
; Syntax.........: Log_Message ( $a_s_Message [, $a_i_MsgType = $GC_I_LOG_MSGTYPE_INFO [, $a_s_Author = "AutoIt" [, $a_h_EditText = 0]]] )
; Parameters ....: $a_s_Message  - String: message text.
;                  $a_i_MsgType  - Integer: one of $GC_I_LOG_MSGTYPE_*. Optional (default: $GC_I_LOG_MSGTYPE_INFO).
;                  $a_s_Author   - String: origin tag. Optional (default: "AutoIt").
;                  $a_h_EditText - Handle: RichEdit control for the fallback path; 0 = no UI sink. Optional (default: 0).
; Return values .: None
; Remarks .......: - Colors are BGR (RichEdit convention): do not "fix" them to RGB.
;                  - With neither a callback nor a RichEdit handle, the message is dropped silently by design.
; ===============================================================================================================================
Func Log_Message($a_s_Message, $a_i_MsgType = $GC_I_LOG_MSGTYPE_INFO, $a_s_Author = "AutoIt", $a_h_EditText = 0)
    ; the DEBUG gate runs BEFORE any dispatch, so callback registrants inherit the filter
    If $a_i_MsgType = $GC_I_LOG_MSGTYPE_DEBUG And Not $g_b_DebugMode Then Return

    If $g_s_Log_Callback <> "" Then
        Call($g_s_Log_Callback, $a_s_Message, $a_i_MsgType, $a_s_Author)
        Return
    EndIf

    If $a_h_EditText = 0 Then Return ; no callback, no UI sink: nothing to render into

    Local $l_s_TypeText
    Local $l_i_Color ; BGR
    Switch $a_i_MsgType
        Case $GC_I_LOG_MSGTYPE_DEBUG
            $l_s_TypeText = "DEBUG"
            $l_i_Color = 0xFFA500
        Case $GC_I_LOG_MSGTYPE_WARNING
            $l_s_TypeText = "WARNING"
            $l_i_Color = 0x00C8FF
        Case $GC_I_LOG_MSGTYPE_ERROR
            $l_s_TypeText = "ERROR"
            $l_i_Color = 0x0000CC
        Case $GC_I_LOG_MSGTYPE_CRITICAL
            $l_s_TypeText = "CRITICAL"
            $l_i_Color = 0x0000FF
        Case Else
            $l_s_TypeText = "INFO"
            $l_i_Color = 0x008000
    EndSwitch

    Local $l_s_LogText = "[" & Log_GetCurrentTime() & "] [" & $l_s_TypeText & "] [" & $a_s_Author & "] " & $a_s_Message & @CRLF

    If _GUICtrlRichEdit_GetTextLength($a_h_EditText) > 30000 Then _GUICtrlRichEdit_SetText($a_h_EditText, "")

    _GUICtrlRichEdit_SetSel($a_h_EditText, -1, -1)
    _GUICtrlRichEdit_SetCharColor($a_h_EditText, $l_i_Color)
    _GUICtrlRichEdit_AppendText($a_h_EditText, $l_s_LogText)
    _GUICtrlEdit_Scroll($a_h_EditText, $SB_SCROLLCARET)
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: Log_Debug
; Description ...: Convenience wrapper: Log_Message with $GC_I_LOG_MSGTYPE_DEBUG (subject to the DEBUG gate).
; Syntax.........: Log_Debug ( $a_s_Message [, $a_s_Author = "AutoIt" [, $a_h_EditText = 0]] )
; Parameters ....: $a_s_Message  - String: message text.
;                  $a_s_Author   - String: origin tag. Optional (default: "AutoIt").
;                  $a_h_EditText - Handle: RichEdit fallback sink. Optional (default: 0).
; Return values .: None
; ===============================================================================================================================
Func Log_Debug($a_s_Message, $a_s_Author = "AutoIt", $a_h_EditText = 0)
    Log_Message($a_s_Message, $GC_I_LOG_MSGTYPE_DEBUG, $a_s_Author, $a_h_EditText)
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: Log_Info
; Description ...: Convenience wrapper: Log_Message with $GC_I_LOG_MSGTYPE_INFO.
; Syntax.........: Log_Info ( $a_s_Message [, $a_s_Author = "AutoIt" [, $a_h_EditText = 0]] )
; Parameters ....: $a_s_Message  - String: message text.
;                  $a_s_Author   - String: origin tag. Optional (default: "AutoIt").
;                  $a_h_EditText - Handle: RichEdit fallback sink. Optional (default: 0).
; Return values .: None
; ===============================================================================================================================
Func Log_Info($a_s_Message, $a_s_Author = "AutoIt", $a_h_EditText = 0)
    Log_Message($a_s_Message, $GC_I_LOG_MSGTYPE_INFO, $a_s_Author, $a_h_EditText)
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: Log_Warning
; Description ...: Convenience wrapper: Log_Message with $GC_I_LOG_MSGTYPE_WARNING.
; Syntax.........: Log_Warning ( $a_s_Message [, $a_s_Author = "AutoIt" [, $a_h_EditText = 0]] )
; Parameters ....: $a_s_Message  - String: message text.
;                  $a_s_Author   - String: origin tag. Optional (default: "AutoIt").
;                  $a_h_EditText - Handle: RichEdit fallback sink. Optional (default: 0).
; Return values .: None
; ===============================================================================================================================
Func Log_Warning($a_s_Message, $a_s_Author = "AutoIt", $a_h_EditText = 0)
    Log_Message($a_s_Message, $GC_I_LOG_MSGTYPE_WARNING, $a_s_Author, $a_h_EditText)
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: Log_Error
; Description ...: Convenience wrapper: Log_Message with $GC_I_LOG_MSGTYPE_ERROR.
; Syntax.........: Log_Error ( $a_s_Message [, $a_s_Author = "AutoIt" [, $a_h_EditText = 0]] )
; Parameters ....: $a_s_Message  - String: message text.
;                  $a_s_Author   - String: origin tag. Optional (default: "AutoIt").
;                  $a_h_EditText - Handle: RichEdit fallback sink. Optional (default: 0).
; Return values .: None
; ===============================================================================================================================
Func Log_Error($a_s_Message, $a_s_Author = "AutoIt", $a_h_EditText = 0)
    Log_Message($a_s_Message, $GC_I_LOG_MSGTYPE_ERROR, $a_s_Author, $a_h_EditText)
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: Log_Critical
; Description ...: Convenience wrapper: Log_Message with $GC_I_LOG_MSGTYPE_CRITICAL.
; Syntax.........: Log_Critical ( $a_s_Message [, $a_s_Author = "AutoIt" [, $a_h_EditText = 0]] )
; Parameters ....: $a_s_Message  - String: message text.
;                  $a_s_Author   - String: origin tag. Optional (default: "AutoIt").
;                  $a_h_EditText - Handle: RichEdit fallback sink. Optional (default: 0).
; Return values .: None
; ===============================================================================================================================
Func Log_Critical($a_s_Message, $a_s_Author = "AutoIt", $a_h_EditText = 0)
    Log_Message($a_s_Message, $GC_I_LOG_MSGTYPE_CRITICAL, $a_s_Author, $a_h_EditText)
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: Log_SetDebugMode
; Description ...: Toggles $g_b_DebugMode and logs the change as INFO (INFO so the "Disabled" message is not
;                  swallowed by the very gate it just enabled).
; Syntax.........: Log_SetDebugMode ( [$a_b_Enable = True] )
; Parameters ....: $a_b_Enable - Boolean: new debug-mode state. Optional (default: True).
; Return values .: None
; ===============================================================================================================================
Func Log_SetDebugMode($a_b_Enable = True)
    $g_b_DebugMode = $a_b_Enable
    Log_Message("Debug Mode " & ($a_b_Enable ? "Enabled" : "Disabled"), $GC_I_LOG_MSGTYPE_INFO, "SetDebugMode")
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: Log_GetCurrentTime
; Description ...: Returns the current time formatted "HH:MM:SS" for log timestamps.
; Syntax.........: Log_GetCurrentTime ( )
; Parameters ....: None
; Return values .: "HH:MM:SS" string.
; ===============================================================================================================================
Func Log_GetCurrentTime()
    Return StringFormat("%02d:%02d:%02d", @HOUR, @MIN, @SEC)
EndFunc