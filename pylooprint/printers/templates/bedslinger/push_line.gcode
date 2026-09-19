;----- push line @INDEX@ of @TOTAL@: @PART_LIST@ -----
G0 X@X@ F@ALIGN_FEED@ ; across the plate at the travel height: at Z@TRAVEL_Z@ a part in the way is shoved aside, never struck from above
G1 Z@Z@ F600	; up to @PUSH_FACTOR@ of the shortest part on this line - at a new X, Z only ever goes up
M400 P100
@PUSH_MOVES@
M400 ; wait for the push to finish
G1 Y@Y_FORWARD@ F800	; bed back along the band just swept, at the same height
G1 Z@TRAVEL_Z@ F600	; back to the travel height, at a point the nozzle has already been
