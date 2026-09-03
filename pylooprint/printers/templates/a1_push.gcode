M220 S100 ; Reset to standard speed for safe push-off
;===== CRITICAL: Align nozzle X-position with model center before push =====
; After cooldown sequence, toolhead is at X-48 (A1) or X-13 (A1 Mini). We must move it to model center
; before the bed moves forward (Y-0.5), otherwise the push will miss the model.
G0 X{first_layer_center_no_wipe_tower[0]} F@ALIGN_FEED@ ; Align nozzle with model center for push

;===== Z-Drop Logic =====
; Push at @PUSH_FACTOR@ of the model height: high enough on the side wall to tip the part
; over, and still below its top edge.
; Under @PUSH_MIN_HEIGHT@ mm there is no useful height left to aim at, so the nozzle
; comes down to Z@PUSH_MIN_Z@ and shoves the part along the plate instead.
{if (max_layer_z ) >= @PUSH_MIN_HEIGHT@}
    G1 Z{max_layer_z * @PUSH_FACTOR@} F600
{else}
    G1 Z@PUSH_MIN_Z@ F600
{endif}

M400 P100											

;===== Main Push Movement (Y-axis, bed moves) =====
; F300 is deliberately slow: the bed is moving under the part, and a quick shove tips it over instead of sliding it off.
G1 Y-0.5 F300		; very slow push off using the x gantry
M400 ; Wait for push to complete before next move

;======== Push off complete, start safety clear / side push off ======
G1 Y180 F800	;move bed forward again (A1: Y262, A1 Mini: Y180)
G1 Z1 F600		;move nozzle closer to the bed when using tall parts