#include-once

#Region Logging System
; Logging related constants and variables
Global $g_b_DebugMode = False

; Log message types
Global Enum $GC_I_LOG_MSGTYPE_DEBUG = 0, _ ; Detailed information for debugging purposes
		$GC_I_LOG_MSGTYPE_INFO, _ ; General operational information
		$GC_I_LOG_MSGTYPE_WARNING, _ ; Warning messages for potential issues
		$GC_I_LOG_MSGTYPE_ERROR, _ ; Error messages for operation failures
		$GC_I_LOG_MSGTYPE_CRITICAL ; Critical errors requiring immediate attention
#EndRegion Logging System