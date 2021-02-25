#!/usr/bin/python
import subprocess
import sys
import os
import json
from datetime import datetime
import config

import RPi.GPIO as GPIO
import Adafruit_DHT

os.environ['PYTHON_EGG_CACHE'] = '__pycache__'
APP_PATH = os.path.dirname(os.path.abspath(__file__))


class thermostat:
	

	__db = {}

	def __init__(self, **kwargs):
		# Setup GPIO
		GPIO.setmode(GPIO.BCM)
		GPIO.setwarnings(False)

		GPIO.setup([config.HEAT_PIN, config.COOL_PIN], GPIO.OUT)

		if (config.HEAT_TWO_STAGE):
			GPIO.setup([config.HEAT_STAGE_2_PIN], GPIO.OUT)
		if (config.COOL_TWO_STAGE):
			GPIO.setup([config.COOL_STAGE_2_PIN], GPIO.OUT)

		self.__load_db()

		return

	''' Read-only attribute'''
	@property
	def Target_Temperature(self):
		return self.__db["target_temperature"]
	@property
	def Mode(self):
		return self.__db["mode"]
	@property
	def Schedule(self):
		return self.__db["schedule"]
	@property
	def Current_Temperature(self):
		sensor = Adafruit_DHT.DHT22
		humidity, temp = Adafruit_DHT.read_retry(sensor, config.SENSOR_PIN)
		temp = round(temp * 9/5.0 + 32, 2) + config.CALIBRATION
		return temp

	@property
	def Current_Temperature_Humidity(self):
		sensor = Adafruit_DHT.DHT22
		humidity, temp = Adafruit_DHT.read_retry(sensor, config.SENSOR_PIN)
		temp = round(temp * 9/5.0 + 32, 2) + config.CALIBRATION
		humidity = round(humidity, 2)
		return temp, humidity
	
	@property
	def Status(self):
		if config.HEAT_TWO_STAGE and GPIO.input(config.HEAT_STAGE_2_PIN) == GPIO.LOW:
			return "HEAT", "2"
		elif config.COOL_TWO_STAGE and GPIO.input(config.COOL_STAGE_2_PIN) == GPIO.LOW:
			return "COOL", "2"
		elif GPIO.input(config.HEAT_PIN) == GPIO.LOW:
			return "HEAT", "1" if config.HEAT_TWO_STAGE else ""
		elif GPIO.input(config.COOL_PIN) == GPIO.LOW:
			return "COOL", "1" if config.COOL_TWO_STAGE else ""
		else:
			return "OFF", ""

	
	def Set(self, targetTemp, Mode, schedule=None):

		if (schedule==None):
			schedule = datetime.now().strftime('%Y-%m-%d %H:%M')

		self.__db["mode"]=Mode
		self.__db["target_temperature"]=int(targetTemp)
		self.__db["schedule"]=schedule
		self.__save_db()
		if config.PERFORM_IMIDIATE_ACTION or Mode == "OFF":
			self.Process()

	def Process(self):
		temp = self.Current_Temperature
		mode = self.__db["mode"]
		target_temperature = self.__db["target_temperature"]
		schedule = self.__db["schedule"]
		schedule = datetime.strptime(schedule, '%Y-%m-%d %H:%M')

		# LOW = ON
		# HIGH = OFF

		# Perfrom process only if current date and time aftre scheduled one except "OFF". "OFF" performed imideately
		if (datetime.now() > schedule or mode=="OFF"):
			if target_temperature - temp > 3 and (mode == "HEAT" or mode == "AUTO"):
				# Set HEAT_2=ON, COOL=OFF
				GPIO.output([config.HEAT_PIN, config.COOL_PIN],(GPIO.LOW, GPIO.HIGH))
				if (config.HEAT_TWO_STAGE):
					GPIO.output([config.HEAT_STAGE_2_PIN],GPIO.LOW)
				if (config.COOL_TWO_STAGE):
					GPIO.output([config.COOL_STAGE_2_PIN],GPIO.HIGH)
				return "ON"
			elif target_temperature - temp > 1 and (mode == "HEAT" or mode == "AUTO"):
				# Set HEAT_1=ON, COOL=OFF
				GPIO.output([config.HEAT_PIN, config.COOL_PIN],(GPIO.LOW, GPIO.HIGH))
				if (config.HEAT_TWO_STAGE):
					GPIO.output([config.HEAT_STAGE_2_PIN],GPIO.HIGH)
				if (config.COOL_TWO_STAGE):
					GPIO.output([config.COOL_STAGE_2_PIN],GPIO.HIGH)

				return "ON"
			elif temp - target_temperature > 3 and (mode == "COOL" or mode == "AUTO"):
				# Set HEAT=OFF, COOL=ON"
				GPIO.output([config.HEAT_PIN, config.COOL_PIN],(GPIO.HIGH, GPIO.LOW))
				if (config.HEAT_TWO_STAGE):
					GPIO.output([config.HEAT_STAGE_2_PIN],GPIO.HIGH)
				if (config.COOL_TWO_STAGE):
					GPIO.output([config.COOL_STAGE_2_PIN],GPIO.LOW)
				return "ON"
			elif temp - target_temperature > 1 and (mode == "COOL" or mode == "AUTO"):
				# Set HEAT = OFF, COOL=ON
				GPIO.output([config.HEAT_PIN, config.COOL_PIN],(GPIO.HIGH, GPIO.LOW))
				if (config.HEAT_TWO_STAGE):
					GPIO.output([config.HEAT_STAGE_2_PIN],GPIO.HIGH)
				if (config.COOL_TWO_STAGE):
					GPIO.output([config.COOL_STAGE_2_PIN],GPIO.HIGH)
				return "ON"
			else:
				GPIO.output([config.HEAT_PIN, config.COOL_PIN],(GPIO.HIGH, GPIO.HIGH))
				if (config.HEAT_TWO_STAGE):
					GPIO.output([config.HEAT_STAGE_2_PIN],GPIO.HIGH)
				if (config.COOL_TWO_STAGE):
					GPIO.output([config.COOL_STAGE_2_PIN],GPIO.HIGH)
				return "OFF"
			GPIO.cleanup()

	def __load_db(self):
		if (os.path.exists(APP_PATH + "/db.json")):
			with open(APP_PATH + '/db.json', 'r') as db_file:
				self.__db = json.load(db_file)
		else:
			self.__db = {"mode": "OFF",
				   "target_temperature": 72,
				   "schedule": datetime.now().isoformat()}
			self.__save_db()
		return

	def __save_db(self):
		with open(APP_PATH + "/db.json", "w+") as db_file:
			db_file.write(json.dumps(self.__db, indent=4))
		return

def get():
	t = thermostat()
	tp,h=t.Current_Temperature_Humidity
	s,st=t.Status
	print(" ")
	print("Temperature: " +str(tp) + "°F")
	print("Humidity: " +str(h) + "%") 
	print("Status: " + s + " " + str(st))
	print(" ")
	print ("Mode: " + str(t.Mode))
	print ("Target Temperature: " + str(t.Target_Temperature) +  "°F")
	print ("Schedule: " + str(t.Schedule))
	print(" ")

def set():
	t=thermostat()
	targetTemp=t.Target_Temperature
	mode=t.Mode
	schedule = None
	a=sys.argv
	i=2
	while i < len(a):
		if  a[i]=="-t" and a[i+1]!='':
			targetTemp=a[i+1]
			i+=2
			continue
		if a[i]=="-m" and a[i+1]!='':
			mode=a[i+1]
			i+=2
			continue
		if a[i]=="-s" and a[i+1]!='':
			schedule=a[i+1]
			i+=2
			continue	
		i+=1
	t.Set(targetTemp,mode,schedule)
	get()

def proc():
	t=thermostat()
	t.Process()
	

if (__name__=="__main__"):
	if (len(sys.argv)<=1):
		get()
	elif sys.argv[1]=="get":
		get()
	elif sys.argv[1]=="set":
		set()
	elif sys.argv[1]=="proc":
		proc()
	else:
		get()

		
			

