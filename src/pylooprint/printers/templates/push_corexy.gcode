M220 S100 ; Reset to standard speed for safe push-off
G1 X@X_START@ Y254 F600		; move nozzle a little to the side for safety
M400				; Wait all motion done
; --- DYNAMIC MULTI-LANE PUSH SYSTEM (Looprint) ---
; Model center calculated from G-code: X@X_CENTER@
; Left lane: X@X_LEFT@ (center - 30mm), Right lane: X@X_RIGHT@ (center + 30mm)
; Push-off speed: @PUSH_SPEED@mm/min

; --- PUSH LANE 1: CENTER (Primary push force at model center) ---
G1 X@X_CENTER@ Y230 F1200 	; take start position at model center
G1 X@X_CENTER@ Y5 F@PUSH_SPEED@		; Push center lane (pushed to Y5 for maximum clearance)
G1 Y230 F5000               ; Retract back for safety

; --- PUSH LANE 2: LEFT (30mm left of center for stability) ---
G1 X@X_LEFT@ Y230 F1200 	; take start position at left lane
G1 X@X_LEFT@ Y5 F@PUSH_SPEED@		; Push left lane (pushed to Y5 for maximum clearance)
G1 Y230 F5000               ; Retract back for safety

; --- PUSH LANE 3: RIGHT (30mm right of center for stability) ---
G1 X@X_RIGHT@ Y230 F1200 	; take start position at right lane
G1 X@X_RIGHT@ Y5 F@PUSH_SPEED@		; Push right lane (pushed to Y5 for maximum clearance)
G1 Y230 F5000               ; Retract back for safety
