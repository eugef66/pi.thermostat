#!/usr/bin/python

# This scrpt is used to retrive current temperature and humidity from temp sensor
import thermostat as th
import os
os.environ['PYTHON_EGG_CACHE'] = '__pycache__' 

t=th.thermostat()
tp,h=t.Current_Temperature_Humidity
s,st=t.Status
print('{"Current_Temperature":'+str(tp)+',"Current_Humidity":' +str(h) + ',"Status":"' +s+'","Mode":"'+ str(t.Mode) +'","Target_Temperature":'+ str(t.Target_Temperature) + ',"Stage":' + str(st) +'}')



