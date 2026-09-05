;----- push line @INDEX@ of @TOTAL@: @PART_LIST@ -----
G1 Z@SAFE_Z@ F600	; lift clear of everything still standing on the plate
G0 X@X@ F@ALIGN_FEED@ ; align the blade with this line
G1 Z@Z@ F600	; down to @PUSH_FACTOR@ of the shortest part on this line
M400 P100
G1 Y-0.5 F300		; push: the bed drives the parts into the blade, slowly
M400 ; wait for the push to finish
G1 Z@SAFE_Z@ F600	; lift before the bed comes back, or the blade drags through what is left
G1 Y@Y_FORWARD@ F800	; bed back, ready for the next line
