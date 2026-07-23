;===== date: 20231229 =====================
;Made by FactorianDesigns, please completely watch the related Youtube video before you try this out

;turn off nozzle clog detect
G392 S0

M400 ; wait for buffer to clear
G92 E0 ; zero the extruder
G1 E-0.8 F1800 ; retract
G1 Z{max_layer_z + 0.5} F900 ; lower z a little
G1 X0 Y{first_layer_center_no_wipe_tower[1]} F18000 ; move to safe pos
G1 X-13.0 F3000 ; move to safe pos

M140 S0 ; turn off bed
M106 S0 ; turn off fan
M106 P2 S0 ; turn off remote part cooling fan
M106 P3 S0 ; turn off chamber cooling fan

; pull back filament to AMS
M620 S255
G1 X181 F12000
T255
G1 X0 F18000
G1 X-13.0 F3000
G1 X0 F18000 ; wipe
M621 S255

M104 S0 ; turn off hotend

M400 ; wait all motion done
M17 S
M17 Z0.4 ; lower z motor current to reduce impact if there is something in the bottom

G90
G1 X-13 Y185 F3600 ; move to safe limit position on the left

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

@PUSH@