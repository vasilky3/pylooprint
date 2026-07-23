;===== Negative Z Push-Off Sequence (Advanced - A1 Only) =====
; WARNING: This uses negative Z values. Only use if you do NOT have Z-axis stiffener mod installed.
; Nozzle head must be at X-48 (far left) for this to work safely.
G1 Z1 F600 ;travel to safe z
G4 S1		;wait 1 second
G1 Z-17 F600 ;go into negative z be very careful here
M400 P100											
G1 Y200 F100			; part release using the x gantry
G1 Y262 F2000			; reset position
G1 Z{max_layer_z +5}	; lift Z into positive again dont erase