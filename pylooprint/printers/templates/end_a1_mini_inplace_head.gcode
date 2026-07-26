;======= turn on fan =================
G90
M17 R
G1 X-13 Y180 Z@PARK_Z@ F3600 ; move to safe limit position on the left
M400 ; wait all motion done

;======= Start Cool Down =============

@M190@

M140 S0 ; turn off bed
				
;======= Cool Down Done, Start Push Off =============
; calculate a good z-pushoff height, BE CAREFUL this could be a little different for parts
; that are fragile in the top, parts below 32 mm heigth can't be pushed off using the gantry
; if your part is too small then use the extruder head for push off and comment out the line "G1 Y1 F300"
; Use the safety clear part as pushoff template and adjust the coordinates as you see fit for you part 

; Enable travel moves and look at the last layer to see what your printer is doing using this code
; YOU NEVER want any -Z values in this or the resulting sliced g-code

M17 S
M17 Z0.4 ; lower z motor current to reduce impact if there is something in the bottom
G1 Z1 F3600 ; return to base position, should save from hiting objects

