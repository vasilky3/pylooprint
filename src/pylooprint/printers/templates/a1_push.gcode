M220 S100 ; Reset to standard speed for safe push-off
;===== CRITICAL: Align nozzle X-position with model center before push =====
; After cooldown sequence, toolhead is at X-48 (A1) or X-13 (A1 Mini). We must move it to model center
; before the bed moves forward (Y-0.5), otherwise the push will miss the model.
; (This alignment move is not in End_A1.txt but is critical for push accuracy)
G0 X{first_layer_center_no_wipe_tower[0]} F@ALIGN_FEED@ ; Align nozzle with model center for push

;===== Z-Drop Logic (41mm Rule) =====
; Factorian's exact conditional from End_A1.txt lines 175-179: IF (max_layer_z ) > 41 THEN Z = max_layer_z - 40 ELSE Z = 1.0
; Note: Factorian uses conditional logic with space after max_layer_z - our regex handles this format
{if (max_layer_z ) > 41}
    G1 Z{max_layer_z - 40} F600
{else}
    G1 Z1 F600
{endif}

M400 P100											

;===== Main Push Movement (Y-axis, bed moves) =====
; Factorian Speed: F300 (very slow to prevent tipping on moving bed) - End_A1.txt line 182, End_A1_Mini.txt line 186
G1 Y-0.5 F300		; very slow push off using the x gantry
; Note: Factorian's End_A1.txt line 182 has no M400 after push, but we add it for safety
M400 ; Wait for push to complete before next move

;======== Push off complete, start safety clear / side push off ======
G1 Y180 F800	;move bed forward again (A1: Y262, A1 Mini: Y180)
G1 Z1 F600		;move nozzle closer to the bed when using tall parts