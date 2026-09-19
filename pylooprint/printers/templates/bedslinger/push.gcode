M220 S100 ; Reset to standard speed for safe push-off
;===== One-line push: the parts could not be measured, so aim at the model's centre =====
G0 X@X@ F@ALIGN_FEED@ ; align the nozzle with the model centre before the bed moves, or the push misses

;===== Push height =====
; @PUSH_FACTOR@ of the model height: high enough on the side wall to tip the part over, still below its top.
; Under @PUSH_MIN_HEIGHT@ mm there is no useful height to aim at, so the nozzle comes down to Z@PUSH_MIN_Z@
; and shoves the part along the plate instead.
G1 Z@Z@ F600

M400 P100

;===== Push (Y axis, the bed moves) =====
; F300 is deliberately slow: the bed is moving under the part, and a quick shove tips it over instead of sliding it off.
G1 Y-0.5 F300		; very slow push-off
M400 ; wait for the push to complete before the next move

;======== Push-off complete, start the sweep ======
G1 Y@Y_FORWARD@ F800	;move bed forward again
G1 Z@PUSH_MIN_Z@ F600		;down to the travel height for the sweep
