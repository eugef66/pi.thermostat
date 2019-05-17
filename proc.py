#!/usr/bin/python

#This script is scheduled in pi:crontab too run every minute to turn termostat on/off based on current and target temperature

import thermostat as th


t=th.thermostat()
t.Process()
