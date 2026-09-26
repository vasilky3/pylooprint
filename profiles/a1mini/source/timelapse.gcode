{if !spiral_mode && print_sequence != "by object"}
; SKIPPABLE_START
; SKIPTYPE: timelapse
M622.1 S1
M1002 judge_flag timelapse_record_flag
M622 J1
G92 E0
G1 E-0.8 F1800
M400
M1004 S5 P1  ; external shutter
M400 P300
M971 S11 C11 O0
G92 E0
G1 E0.8 F1800
G92 E0
M623
; SKIPPABLE_END
{endif}