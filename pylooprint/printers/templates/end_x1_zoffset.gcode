
;=== Cool Down Done, Start Push Off ===  
;!!! CAREFUl !!! You have to enter your own print specific coordinates below, or this will damage your printer !!!
; if you push of multiple objects then always start from right to left so you don't hit your LIDAR, this only works with small objects 
; The following lines raise the bed to initiate the push off, your model height -30 mm is often a good pushoff point for you extruder head not to hit any fans or the nozzle
; I have updated the automatic z calculation so if your print is over 31 mm tall the nozzle doesn't hit your bed but feel free to enter your own z height if necessary

; Auto calculation to raise bed

M400
{if (max_layer_z ) > 31}
    G1 Z{max_layer_z - 30} F600
{else}
    G1 Z1 F600
{endif}
M400 P100
