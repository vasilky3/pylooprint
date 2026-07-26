
; ====== Cool Down =====
M400 				;wait for all print moves to be done											 
M17 Z0.4 			;lower z motor current to reduce impact if there is something in the top																					
G1 Z1 F600 			;move nozzle up, BE VERY CAREFUL this can hit the top of your print, extruder or AMS
M400				;wait all motion done
M106 P2 S255 		;turn Aux fan on
M106 P3 S200 		;turn on chamber cooling fan
