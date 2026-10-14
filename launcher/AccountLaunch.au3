#include-once
; Adapted from Encounter ReBuilt PUBLIC / Files/Launch.au3 (KleuTSchi, Greg).
; Suspended launch, multiclient patch, job-object child tracking and argument quoting.
#include "AccountSecurity.au3"
Global Const $GC_I_ERROR_ALREADY_EXISTS = 183
Global Const $GC_I_WAIT_TIMEOUT = 0x00000102
Global Const $GC_S_GWPROCESS_GAME_CLASS = "ArenaNet_Dx_Window_Class"
Global Const $GC_S_GWPROCESS_GAME_EXE = "Gw.exe"
Global $g_h_GameMutex = 0

Func Launch_JobObjectEnumPIDs($a_h_Job)
    Local Const $LC_I_BUFFER = 16
    Local $l_d_ProcessListInfo = DllStructCreate($tagJOBOBJECT_BASIC_PROCESS_ID_LIST & ";ulong_ptr ProcessIdList[" & $LC_I_BUFFER & "]")
    Local $l_av_Result = DllCall("kernel32.dll", "bool", "QueryInformationJobObject", _
        "handle", $a_h_Job, _
        "int", 3, _
        "ptr", DllStructGetPtr($l_d_ProcessListInfo), _
        "dword", DllStructGetSize($l_d_ProcessListInfo), _
        "dword*", 0)
    If @error Or Not $l_av_Result[0] Then Return SetError(1, 0, 0)

    Local $l_i_Count = DllStructGetData($l_d_ProcessListInfo, "NumberOfProcessIdsInList")
    If $l_i_Count > $LC_I_BUFFER Then $l_i_Count = $LC_I_BUFFER

    Local $l_av_PIDs[$l_i_Count]
    For $l_i_Idx = 1 To $l_i_Count
        $l_av_PIDs[$l_i_Idx - 1] = DllStructGetData($l_d_ProcessListInfo, "ProcessIdList", $l_i_Idx)
    Next
    Return $l_av_PIDs
EndFunc

Func Launch_ProcessWindowOfClass($a_i_PID, $a_s_Class)
    Local $l_av_Windows = WinList("[CLASS:" & $a_s_Class & "]")
    If Not IsArray($l_av_Windows) Then Return 0
    For $l_i_Idx = 1 To $l_av_Windows[0][0]
        Local $l_h_Wnd = $l_av_Windows[$l_i_Idx][1]
        If WinGetProcess($l_h_Wnd) = $a_i_PID Then
            Return $l_h_Wnd
        EndIf
    Next
    Return 0
EndFunc

Func Launch_WaitForPlayablePID($a_i_RootPID, $a_h_Job, $a_i_WindowGraceMs, $a_i_OverallTimeoutMs)
    Local $l_i_T0 = TimerInit()
    Local $l_i_TGrace = TimerInit()
    Local $l_s_Exe = StringLower($GC_S_GWPROCESS_GAME_EXE)

    While TimerDiff($l_i_T0) < $a_i_OverallTimeoutMs
        ; (Path A) RootPID shows the expected window within grace period
        If ProcessExists($a_i_RootPID) And TimerDiff($l_i_TGrace) <= $a_i_WindowGraceMs Then
            If Launch_ProcessWindowOfClass($a_i_RootPID, $GC_S_GWPROCESS_GAME_CLASS) Then
                Return $a_i_RootPID
            EndIf
        EndIf

        ; (Path B) Any non-root Gw.exe inside the job shows expected window
        Local $l_av_PIDs = Launch_JobObjectEnumPIDs($a_h_Job)
        If IsArray($l_av_PIDs) Then
            For $l_i_Idx = 0 To UBound($l_av_PIDs) - 1
                Local $l_i_PID = $l_av_PIDs[$l_i_Idx]
                If $l_i_PID = 0 Or $l_i_PID = $a_i_RootPID Then ContinueLoop
                If Not ProcessExists($l_i_PID) Then ContinueLoop

                Local $l_s_FileName = _WinAPI_GetProcessFileName($l_i_PID)
                If @error Or $l_s_FileName = "" Then ContinueLoop
                Local $l_s_Base = StringLower(StringRegExpReplace($l_s_FileName, "^.*\\", ""))
                If $l_s_Base <> $l_s_Exe Then ContinueLoop
                
                $l_i_TGrace = TimerInit()
                While TimerDiff($l_i_TGrace) < $a_i_WindowGraceMs
                    If Not ProcessExists($l_i_PID) Then Return SetError(1, 0, 0)
                    If Launch_ProcessWindowOfClass($l_i_PID, $GC_S_GWPROCESS_GAME_CLASS) Then
                        Return $l_i_PID
                    EndIf
                    Sleep(150)
                WEnd
            Next
        EndIf
        Sleep(150)
    WEnd

    Return SetError(1, 0, 0)
EndFunc

Func Launch_LaunchAccountFromINI($a_s_IniFile, $a_s_Character, $a_b_Restart = False, $a_s_ExeOverride = "", $a_s_Seed = "Encounter_ReBuilt.au3")
    Local $l_i_Timeout = 10000
    Local $l_h_IniMutex = Security_AcquireFileMutex($a_s_IniFile, $l_i_Timeout)
    If $l_h_IniMutex <= 0 Then Return 0

    Local $l_s_Email = IniRead($a_s_IniFile, $a_s_Character, "Email", "")
    Local $l_s_Pwd = Security_DecryptString(IniRead($a_s_IniFile, $a_s_Character, "Pwd", ""), $a_s_Seed)
    If @error Or $l_s_Pwd = "" Or $l_s_Email = "" Then
        Security_CloseMutex($l_h_IniMutex)
        AddOns_Out("[ERR] Missing credentials or password decryption failed; check encryption seed")
        Return 0
    EndIf
    Local $l_s_FilePath = IniRead($a_s_IniFile, $a_s_Character, "FilePath", "")
    
    Security_CloseMutex($l_h_IniMutex)
    If $a_s_ExeOverride <> "" Then $l_s_FilePath = $a_s_ExeOverride

    If Not FileExists($l_s_FilePath) Then
        AddOns_Out("[ERR] Could not find Guild Wars executable (Gw.exe): " & $l_s_FilePath)
        Return 0
    EndIf

    Local $l_s_GameMutex = "AU3-Mutex-Window-Guild Wars-" & $a_s_Character
    If $a_b_Restart Then Security_CloseMutex($g_h_GameMutex)

    $g_h_GameMutex = _WinAPI_CreateMutex($l_s_GameMutex)
    If $g_h_GameMutex = 0 Then
        AddOns_Out("[ERR] Failed to create/open mutex object: " & $l_s_GameMutex)
        Return 0
    EndIf

    Local $l_i_LastErr = _WinAPI_GetLastError()
    If $l_i_LastErr = $GC_I_ERROR_ALREADY_EXISTS Then
        AddOns_Out("[ERR] Mutex object already exists: " & $l_s_GameMutex)
        Security_CloseMutex($g_h_GameMutex)
        Return 0
    EndIf

    AddOns_Out("[INIT] Launching account")
    AddOns_Out("[INIT] Character: " & $a_s_Character)

    Local $l_s_Args = ' -fps 30'
    $l_s_Args &= ' -character ' & Launch_QuoteArg($a_s_Character)
    $l_s_Args &= ' -email ' & Launch_QuoteArg($l_s_Email)  
    $l_s_Args &= ' -password ' & Launch_QuoteArg($l_s_Pwd)

    Local $l_s_Cmd = Launch_QuoteArg($l_s_FilePath) & $l_s_Args

    If Not StringInStr($l_s_FilePath, '\') Then
        AddOns_Out("[ERR] Invalid File Path: " & $l_s_FilePath)
        Security_CloseMutex($g_h_GameMutex)
        Return 0
    EndIf
    Local $l_s_WorkingDir = StringRegExpReplace($l_s_FilePath, "^(.*\\).*?$", "$1")

    Local $l_d_StartupInfo = DllStructCreate($tagSTARTUPINFO)
    Local $l_d_ProcessInfo = DllStructCreate($tagPROCESS_INFORMATION)
    DllStructSetData($l_d_StartupInfo, "Size", DllStructGetSize($l_d_StartupInfo))

    Local $l_av_Result = DllCall("kernel32.dll", "bool", "CreateProcessW", _
        "wstr", $l_s_FilePath, _
        "wstr", $l_s_Cmd, _
        "ptr", 0, _
        "ptr", 0, _
        "bool", False, _
        "dword", $CREATE_SUSPENDED, _
        "ptr", 0, _
        "wstr", $l_s_WorkingDir, _
        "struct*", $l_d_StartupInfo, _
        "struct*", $l_d_ProcessInfo)

    If @error Or Not $l_av_Result[0] Then
        AddOns_Out("[ERR] Failed to launch process")
        Security_CloseMutex($g_h_GameMutex)
        Return 0
    EndIf

    Local $l_h_Process = DllStructGetData($l_d_ProcessInfo, "hProcess")
    Local $l_h_Thread = DllStructGetData($l_d_ProcessInfo, "hThread")
    Local $l_i_PID = DllStructGetData($l_d_ProcessInfo, "ProcessId")

    Local $l_h_Job = _WinAPI_CreateJobObject()
    If @error Or $l_h_Job = 0 Then
        AddOns_Out("[ERR] Failed to create job object, PID-chain of launcher cannot be tracked")
        DllCall("kernel32.dll", "bool", "TerminateProcess", "handle", $l_h_Process, "uint", 1)
        _WinAPI_CloseHandle($l_h_Thread)
        _WinAPI_CloseHandle($l_h_Process)
        Security_CloseMutex($g_h_GameMutex)
        Return 0
    EndIf

    If Not _WinAPI_AssignProcessToJobObject($l_h_Job, $l_h_Process) Then
        AddOns_Out("[ERR] Failed to assign process to job object")
        DllCall("kernel32.dll", "bool", "TerminateProcess", "handle", $l_h_Process, "uint", 1)
        _WinAPI_CloseHandle($l_h_Thread)
        _WinAPI_CloseHandle($l_h_Process)
        _WinAPI_CloseHandle($l_h_Job)
        Security_CloseMutex($g_h_GameMutex)
        Return 0
    EndIf

    If Not Launch_ApplyMultiClientPatch($l_h_Process) Then
        AddOns_Out("[ERR] Failed to apply MultiClient patch")
        DllCall("kernel32.dll", "bool", "TerminateProcess", "handle", $l_h_Process, "uint", 1)
        _WinAPI_CloseHandle($l_h_Thread)
        _WinAPI_CloseHandle($l_h_Process)
        _WinAPI_CloseHandle($l_h_Job)
        Security_CloseMutex($g_h_GameMutex)
        Return 0
    EndIf

    Local $l_av_Resume = DllCall("kernel32.dll", "dword", "ResumeThread", "handle", $l_h_Thread)
    If @error Or $l_av_Resume[0] = -1 Then
        AddOns_Out("[ERR] Failed to resume thread")
        DllCall("kernel32.dll", "bool", "TerminateProcess", "handle", $l_h_Process, "uint", 1)
        _WinAPI_CloseHandle($l_h_Thread)
        _WinAPI_CloseHandle($l_h_Process)
        _WinAPI_CloseHandle($l_h_Job)
        Security_CloseMutex($g_h_GameMutex)
        Return 0
    EndIf

    Local $l_av_Wait = DllCall("kernel32.dll", "dword", "WaitForSingleObject", "handle", $l_h_Process, "dword", 0)
    If @error Or $l_av_Wait[0] <> $GC_I_WAIT_TIMEOUT Then
        AddOns_Out("[ERR] Process not running after resume")
        DllCall("kernel32.dll", "bool", "TerminateProcess", "handle", $l_h_Process, "uint", 1)
        _WinAPI_CloseHandle($l_h_Thread)
        _WinAPI_CloseHandle($l_h_Process)
        _WinAPI_CloseHandle($l_h_Job)
        Security_CloseMutex($g_h_GameMutex)
        Return 0
    EndIf

    _WinAPI_CloseHandle($l_h_Thread)
    _WinAPI_CloseHandle($l_h_Process)

    Local $l_i_WindowGracePeriod = 20000
    Local $l_i_OverallTimeout = 120000
    Local $l_i_UpdatedPID = Launch_WaitForPlayablePID($l_i_PID, $l_h_Job, $l_i_WindowGracePeriod, $l_i_OverallTimeout)
    If @error Or $l_i_UpdatedPID = 0 Then
        AddOns_Out("[ERR] Failed to find playable Gw.exe")
        _WinAPI_CloseHandle($l_h_Job)
        Security_CloseMutex($g_h_GameMutex)
        Return 0
    EndIf

    _WinAPI_CloseHandle($l_h_Job)

    AddOns_Out("[INIT] Successfully launched account")
    AddOns_Out("[INIT] PID: " & $l_i_UpdatedPID)

    Return $l_i_UpdatedPID
EndFunc

Func Launch_QuoteArg($a_s_ArgumentString)
    If $a_s_ArgumentString = "" Then Return '""'

    If Not StringRegExp($a_s_ArgumentString, '[\s"]') Then Return $a_s_ArgumentString

    Local $l_s_ResultQuoted = '"'
    Local $l_i_Index = 1
    Local $l_i_StringLength = StringLen($a_s_ArgumentString)

    While $l_i_Index <= $l_i_StringLength
        Local $l_i_BackslashCount = 0
        While $l_i_Index <= $l_i_StringLength And StringMid($a_s_ArgumentString, $l_i_Index, 1) = '\'
            $l_i_BackslashCount += 1
            $l_i_Index += 1
        WEnd

        If $l_i_Index > $l_i_StringLength Then
            $l_s_ResultQuoted &= _StringRepeat('\', $l_i_BackslashCount * 2)
            ExitLoop
        EndIf

        Local $l_s_CurrentChar = StringMid($a_s_ArgumentString, $l_i_Index, 1)

        If $l_s_CurrentChar = '"' Then
            $l_s_ResultQuoted &= _StringRepeat('\', $l_i_BackslashCount * 2 + 1) & '"'
        Else
            $l_s_ResultQuoted &= _StringRepeat('\', $l_i_BackslashCount) & $l_s_CurrentChar
        EndIf

        $l_i_Index += 1
    WEnd

    $l_s_ResultQuoted &= '"'
    Return $l_s_ResultQuoted
EndFunc

Func Launch_ApplyMultiClientPatch($a_h_Process)
    Local $l_ax_Pattern[19] = [0x56, 0x57, 0x68, 0x00, 0x01, 0x00, 0x00, 0x89, 0x85, _
                              0xF4, 0xFE, 0xFF, 0xFF, 0xC7, 0x00, 0x00, 0x00, 0x00, 0x00]
    Local $l_ax_Patch[4] = [0x31, 0xC0, 0x90, 0xC3]

    Local $l_b_Found = False
    Local $l_p_PatchAddr = 0
    Local $l_i_BlockSize = 0x10000

    Local $l_p_CurrAddr = 0x10000
    Local $l_p_MaxAddr = 0x7FFFFFFF
    Local $l_i_ConsecutiveFailures = 0

    While $l_p_CurrAddr < $l_p_MaxAddr
        Local $l_d_MemInfo = DllStructCreate("ptr BaseAddress;ptr AllocationBase;dword AllocationProtect;ptr RegionSize;dword State;dword Protect;dword Type")
        Local $l_amx_QueryResult = DllCall("kernel32.dll", "ulong_ptr", "VirtualQueryEx", _
            "handle", $a_h_Process, _
            "ptr", $l_p_CurrAddr, _
            "struct*", $l_d_MemInfo, _
            "ulong_ptr", DllStructGetSize($l_d_MemInfo))

        If @error Or $l_amx_QueryResult[0] = 0 Then
            $l_p_CurrAddr += 0x10000
            $l_i_ConsecutiveFailures += 1
            If $l_i_ConsecutiveFailures > 100 Then ExitLoop
            ContinueLoop
        EndIf

        $l_i_ConsecutiveFailures = 0

        Local $l_p_RegionBase = DllStructGetData($l_d_MemInfo, "BaseAddress")
        Local $l_i_RegionSize = DllStructGetData($l_d_MemInfo, "RegionSize")
        Local $l_i_State = DllStructGetData($l_d_MemInfo, "State")
        Local $l_i_Protect = DllStructGetData($l_d_MemInfo, "Protect")

        If $l_i_State = 0x1000 And BitAND($l_i_Protect, 0xEE) > 0 Then
            For $l_i_Offset = 0 To $l_i_RegionSize - 1 Step $l_i_BlockSize
                Local $l_i_ReadSize = $l_i_BlockSize
                If $l_i_Offset + $l_i_ReadSize > $l_i_RegionSize Then
                    $l_i_ReadSize = $l_i_RegionSize - $l_i_Offset
                EndIf

                Local $l_d_Buffer = DllStructCreate("byte[" & $l_i_ReadSize & "]")
                Local $l_i_PatternSize = UBound($l_ax_Pattern)
                Local $l_i_BytesRead = 0

                If _WinAPI_ReadProcessMemory($a_h_Process, $l_p_RegionBase + $l_i_Offset, $l_d_Buffer, $l_i_ReadSize, $l_i_BytesRead) And $l_i_BytesRead >= $l_i_PatternSize Then
                    For $l_i_Pos = 1 To ($l_i_BytesRead - $l_i_PatternSize + 1)
                        Local $l_b_Match = True
                        For $l_i_Byte = 0 To $l_i_PatternSize - 1
                            If DllStructGetData($l_d_Buffer, 1, $l_i_Pos + $l_i_Byte) <> $l_ax_Pattern[$l_i_Byte] Then
                                $l_b_Match = False
                                ExitLoop
                            EndIf
                        Next

                        If $l_b_Match Then
                            $l_p_PatchAddr = $l_p_RegionBase + $l_i_Offset + ($l_i_Pos - 1) - 0x1A
                            ExitLoop 3
                        EndIf
                    Next
                EndIf
            Next
        EndIf
        $l_p_CurrAddr = $l_p_RegionBase + $l_i_RegionSize
    WEnd

    If $l_p_PatchAddr = 0 Then Return False
    Local $l_d_TestRead = DllStructCreate("byte[4]")
    Local $l_i_TestReadBytes = 0
    If Not _WinAPI_ReadProcessMemory($a_h_Process, $l_p_PatchAddr, $l_d_TestRead, 4, $l_i_TestReadBytes) Or $l_i_TestReadBytes <> 4 Then
        Return False
    EndIf

    Local $l_i_OldProtect = 0
    _WinAPI_VirtualProtectEx($a_h_Process, $l_p_PatchAddr, 4, $PAGE_EXECUTE_READWRITE, $l_i_OldProtect)

    Local $l_d_Payload = DllStructCreate("byte[4]")
    For $l_i_Idx = 0 To 3
        DllStructSetData($l_d_Payload, 1, $l_ax_Patch[$l_i_Idx], $l_i_Idx + 1)
    Next

    Local $l_amx_WriteResult = DllCall("kernel32.dll", "bool", "WriteProcessMemory", _
        "handle", $a_h_Process, _
        "ptr", $l_p_PatchAddr, _
        "struct*", $l_d_Payload, _
        "ulong_ptr", 4, _
        "ulong_ptr*", 0)

    DllCall("kernel32.dll", "bool", "FlushInstructionCache", "handle", $a_h_Process, "ptr", $l_p_PatchAddr, "ulong_ptr", 4)
    _WinAPI_VirtualProtectEx($a_h_Process, $l_p_PatchAddr, 4, $l_i_OldProtect, $l_i_OldProtect)

    If @error Or Not IsArray($l_amx_WriteResult) Or $l_amx_WriteResult[5] <> 4 Then
        Return False
    EndIf

    Return True
EndFunc

Func _WinAPI_VirtualProtectEx($a_h_Process, $a_p_Address, $a_i_Size, $a_i_NewProtection, ByRef $a_i_OldProtection)
    Local $l_amx_Result = DllCall("kernel32.dll", "bool", "VirtualProtectEx", _
        "handle", $a_h_Process, _
        "ptr", $a_p_Address, _
        "ulong_ptr", $a_i_Size, _
        "dword", $a_i_NewProtection, _
        "dword*", 0)

    If @error Then
        Return SetError(@error, @extended, False)
    EndIf

    $a_i_OldProtection = $l_amx_Result[5]

    Return $l_amx_Result[0] <> 0
EndFunc
