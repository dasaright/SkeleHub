#include-once

#Region Memory Handles
; Process and memory handles
Global $g_h_Kernel32 = 0 ; Handle to kernel32.dll
Global $g_h_GWProcess = 0  ; Handle to Guild Wars process
Global $g_i_GWProcessId = 0 ; Process ID of Guild Wars client
Global $g_h_GWWindow = 0  ; Window handle of Guild Wars client
Global $g_i_GWExeStart = 0 ; Start timestamp of Guild Wars client
Global $g_p_ASMMemory = 0 ; Memory address where ASM code is stored
#EndRegion Memory Handles