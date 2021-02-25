import os
import web
import thermostat as th
import config
import RPi.GPIO as GPIO


abspath = os.path.abspath(__file__)
dname = os.path.dirname(abspath)
os.chdir(dname)

t=th.thermostat()
web.start()

