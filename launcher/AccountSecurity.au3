#include-once
; Adapted from Encounter ReBuilt PUBLIC / Files/Security.au3 (KleuTSchi).
Global Const $GC_I_WAIT_OBJECT_0 = 0x00000000
Global Const $GC_I_WAIT_ABANDONED = 0x00000080
Global Const $GC_S_SEC_TAG = "{SEC}"
Global Const $GC_S_SEC_TAG_LE = StringLen($GC_S_SEC_TAG)
Func Security_DecryptString($a_s_Crypt, $a_s_Seed)
    If Not IsString($a_s_Crypt) Then Return $a_s_Crypt
    If StringLeft($a_s_Crypt, $GC_S_SEC_TAG_LE) <> $GC_S_SEC_TAG Then Return $a_s_Crypt

    Local $l_s_Hex = "0x" & StringMid($a_s_Crypt, $GC_S_SEC_TAG_LE + 1)
    Local $l_x_Plain = _Crypt_DecryptData($l_s_Hex, $a_s_Seed, $CALG_AES_256)
    If @error Or $l_x_Plain = "" Then
        ; The working farm may have saved credentials from either its source or executable.
        If $a_s_Seed = "Encounter_ReBuilt.au3" Then
            $l_x_Plain = _Crypt_DecryptData($l_s_Hex, "Encounter_ReBuilt.exe", $CALG_AES_256)
            If @error Or $l_x_Plain = "" Then Return SetError(2, 0, "")
        Else
            Return SetError(2, 0, "")
        EndIf
    EndIf

    Return BinaryToString($l_x_Plain, $SB_UTF8)
EndFunc

Func Security_PathToMutexName($a_s_Path)
    Local $l_s_Hash = _Crypt_HashData(StringLower($a_s_Path), $CALG_MD5)
    Return "AU3-Mutex-" & StringTrimLeft($l_s_Hash, 2)
EndFunc

Func Security_AcquireFileMutex($a_s_Path, $a_i_Timeout)
    Local $l_s_Mutex = Security_PathToMutexName($a_s_Path)
    Local $l_av_Create = _WinAPI_CreateMutex($l_s_Mutex)
    If @error Or $l_av_Create = 0 Then
        Return SetError(1, 0, -1)
    EndIf
    Local $l_h_Mutex = $l_av_Create

    Local $l_av_Wait = _WinAPI_WaitForSingleObject($l_h_Mutex, $a_i_Timeout)
    If @error Or ($l_av_Wait <> $GC_I_WAIT_OBJECT_0 And $l_av_Wait <> $GC_I_WAIT_ABANDONED) Then
        _WinAPI_CloseHandle($l_h_Mutex)
        Return SetError(2, 0, -1)
    EndIf

    Return $l_h_Mutex
EndFunc

Func Security_CloseMutex(ByRef $a_h_Mutex)
    If $a_h_Mutex <= 0 Then Return

    _WinAPI_ReleaseMutex($a_h_Mutex)
    _WinAPI_CloseHandle($a_h_Mutex)
    $a_h_Mutex = 0
EndFunc
