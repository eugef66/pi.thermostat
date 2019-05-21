#!/usr/bin/python

# This scrpt is used to set target temperature

import sys
import thermostat as th
import os
os.environ['PYTHON_EGG_CACHE'] = '__pycache__' 
#print (sys.argv)

t=th.thermostat()
targetTemp=t.Target_Temperature
mode=t.Mode

for a in sys.argv:
	if "t=" in a and a[2:]!='':
		targetTemp=a[2:]
		continue
	if "m=" in a and a[2:]!='':
		mode=a[2:]
		continue
#print (targetTemp)
#print (mode)
t.Set(targetTemp,mode)
import get

	



