;===== date: 20230428 ===================== Made by FactorianDesigns, please completely watch the related Youtube video before you try this out
M400 ; wait for buffer to clear
G92 E0 ; zero the extruder
G1 E-0.8 F1800 ; retract
G1 Z{max_layer_z + 0.5} F900 ; lower z a little
G1 X65 Y245 F12000 ; move to safe pos
G1 Y265 F3000

G1 X65 Y245 F12000
G1 Y265 F3000
M140 S0 ; turn off bed
M106 S0 ; turn off fan
M106 P2 S0 ; turn off remote part cooling fan
M106 P3 S0 ; turn off chamber cooling fan

G1 X100 F12000 ; wipe
; pull back filament to AMS
M620 S255
G1 X20 Y50 F12000
G1 Y-3
T255
G1 X65 F12000
G1 Y265
G1 X100 F12000 ; wipe
M621 S255
M104 S0 ; turn off hotend

M622.1 S1 ; for prev firware, default turned on
M1002 judge_flag timelapse_record_flag
M622 J1
    M400 ; wait all motion done
    M991 S0 P-1 ;end smooth timelapse at safe pos
    M400 S3 ;wait for last picture to be taken
M623; end of "timelapse_record_flag"

M400 ; wait all motion done
M17 S
;M17 Z0.4 ; lower z motor current to reduce impact if there is something in the bottom
;{if (max_layer_z + 100.0) < 250}
;    G1 Z{max_layer_z + 100.0} F600
;    G1 Z{max_layer_z +98.0}
;{else}
;    G1 Z250 F600
;    G1 Z248
;{endif}
;M400 P100
;M17 R ; restore z current
                                
; ====== Cool Down =====
M400 				;wait for all print moves to be done											 
M17 Z0.4 			;lower z motor current to reduce impact if there is something in the top																					
G1 Z1 F600 			;move nozzle up, BE VERY CAREFUL this can hit the top of your print, extruder or AMS
M400				;wait all motion done
M106 P2 S255 		;turn Aux fan on
M106 P3 S200 		;turn on chamber cooling fan

M190 S18 ; wait for bed temp, Enter your own target cooldown temperatur here (-3 °C because printer stops cooling down earlier at low temps, here the target temp is 23 °C)
M190 S18 ; wait for bed temp
M190 S18 ; wait for bed temp
M190 S18 ; wait for bed temp
M190 S18 ; wait for bed temp
M190 S18 ; wait for bed temp
M190 S18 ; wait for bed temp
M190 S18 ; wait for bed temp
M190 S18 ; wait for bed temp
M190 S18 ; wait for bed temp
M190 S18 ; wait for bed temp
M190 S18 ; wait for bed temp
M190 S18 ; wait for bed temp
M190 S18 ; wait for bed temp
M190 S18 ; wait for bed temp
M190 S18 ; wait for bed temp
M190 S18 ; wait for bed temp 
M190 S18 ; wait for bed temp 
M190 S18 ; wait for bed temp 
M190 S18 ; wait for bed temp 
M190 S18 ; wait for bed temp 
M190 S18 ; wait for bed temp 
M190 S18 ; wait for bed temp 
M190 S18 ; wait for bed temp 
M190 S18 ; wait for bed temp 
M190 S18 ; wait for bed temp 
M190 S18 ; wait for bed temp 
M190 S18 ; wait for bed temp 
M190 S18 ; wait for bed temp 
M190 S18 ; wait for bed temp 
M190 S18 ; wait for bed temp 
M190 S18 ; wait for bed temp 
M190 S18 ; wait for bed temp 
M190 S18 ; wait for bed temp 
M190 S18 ; wait for bed temp 
M190 S18 ; wait for bed temp 
M190 S18 ; wait for bed temp 
M190 S18 ; wait for bed temp 
M190 S18 ; wait for bed temp 
M190 S18 ; wait for bed temp, total max wait time of all lines = 60 min 
                            
M106 P2 S0 					;turn off Aux fan 
M106 P3 S0					;turn off chamber cooling fan 
                            
;=== Cool Down Done, Start Push Off ===  !!! CAREFUL !!! You have to enter your own print specific coordinates here, or this will damage your printer !!!  
;!!! CAREFUL !!! You have to enter your own print specific coordinates below, or this will damage your printer !!!
; if you push off multiple objects then always start from right to left so you don't hit your LIDAR, this only works with small objects 
; The following lines lower the bed to initiate the push off
; Bed is lowered by 110mm from model height to ensure model top has adequate clearance from printer edge
; This ensures front shield can push model while preventing model top from hitting printer edge

M400
{if (max_layer_z ) > 31}
    G1 Z{max_layer_z - 30} F600
{else}
    G1 Z1 F600
{endif}
M400 P100

;G1 Z1 F600 			; Alternative to z moves lines above

G1 X170 Y254 F600		; move nozzle a little to the side for safety
M400				; Wait all motion done
G1 X120 Y230 F1200 		; take start middle push off position, -8mm in x from center of the print is the center of the toolhead  
G1 X120 Y25 F300		; Very slowly push off

;====Push off complete, start safety clear ==== You can enter your own specific coordinates here as well or erase this part if not wanted

;G1 z1 F600			;uncomment this if you want to do the safety clear at a different height
G1 X120 Y200 F2000 	;take start push off position at back
G1 X180 Y200 F2000 	;move to the right
G1 X180 Y25 F2000 	;push off at right position

G1 X180 Y200 F2000 	;take start push off position at back
G1 X60 Y200 F2000 	;move to the left
G1 X60 Y25 F2000 	;push off at left position

;==== safety clear complete ====
                    
M220 S100  ; Reset feedrate magnitude
M201.2 K1.0 ; Reset acc magnitude
M73.2   R1.0 ;Reset left time magnitude
M1002 set_gcode_claim_speed_level : 0

M17 X0.8 Y0.8 Z0.5 ; lower motor current to 45% power
