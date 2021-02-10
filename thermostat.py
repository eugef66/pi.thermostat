import subprocess
import sys
import os
import config

os.environ['PYTHON_EGG_CACHE'] = '__pycache__' 

#APP_PATH = os.path.dirname(os.path.abspath(__file__))
#if (sys.version_info > (3, 0)):
#	exec(open(APP_PATH + "/thermostat.conf").read())
#else:
#	execfile(APP_PATH + "/thermostat.conf")


import Adafruit_DHT
import RPi.GPIO as GPIO


class thermostat:

	
	__ModeFile="thermostat.dat"
	__ConfigFile="thermostat.conf"

	Target_Temperature = 65
	Mode = "OFF"

	__HEAT_Pin = 2
	__HEAT2_Pin = 17
	__COOL_Pin = 3
	__Sensor_Pin=4

	# Config parammeters
	__Calib=0
	__Immed_action=False


	def __init__(self, **kwargs):
		# Setup GPIO
		GPIO.setmode(GPIO.BCM)
		GPIO.setwarnings(False)
		GPIO.setup([self.__HEAT_Pin,self.__HEAT2_Pin,self.__COOL_Pin],GPIO.OUT)
		
		

		self.__Calib = config.CALIBRATION
		self.__Immed_action = config.PERFORM_IMIDIATE_ACTION
		self.__HEAT_Pin = config.HEAT_PIN
		self.__HEAT2_Pin = config.HEAT_STAGE_2_PIN
		self.__COOL_Pin = config.COOL_PIN
		self.__Sensor_Pin=config.SENSOR_PIN

		# Read config file
		#config_file = open(self.__ConfigFile,"r")
		#for line in config_file:
		#	if line: 
		#		kv = line.split("=")
		#		if kv[0] == "CALIBRATION":
		#			self.__Calib = int(kv[1].strip())
		#			continue
		#		if kv[0] == "PERFORM_IMIDIATE_ACTION":
		#			self.__Immed_action = (kv[1].strip()=="True")
		#			continue
		#print self.__Calib
		#print self.__Immed_action

		# Read mode file 
		mode_file = open(self.__ModeFile,"r")
		for line in mode_file:
			if line: 
				kv = line.split("=")
				if kv[0] == "TargetTemperature":
					self.Target_Temperature = int(kv[1].strip())
					continue
				if kv[0] == "Mode":
					self.Mode = kv[1].strip()
					continue
		
		
		return 
	
	''' Read-only attribute'''
	@property
	def Current_Temperature(self):
		sensor = Adafruit_DHT.DHT22
		humidity, temp = Adafruit_DHT.read_retry(sensor,self.__Sensor_Pin)
		temp = round(temp * 9/5.0 + 32,2)+self.__Calib
		return temp
	
	@property
	def Current_Temperature_Humidity(self):
		sensor = Adafruit_DHT.DHT22
		humidity, temp = Adafruit_DHT.read_retry(sensor,self.__Sensor_Pin)
		temp = round(temp * 9/5.0 + 32,2)+self.__Calib
		humidity=round(humidity,2)
		return temp, humidity
	

	@property 
	def Status(self):
		if GPIO.input(self.__HEAT2_Pin)==GPIO.LOW:
			return "HEAT", "2"
		elif GPIO.input(self.__HEAT_Pin)==GPIO.LOW:
			return "HEAT", "1"
		elif GPIO.input(self.__COOL_Pin)==GPIO.LOW:
			return "COOL", ""
		else:
			return "OFF", ""

	def Set(self, targetTemp, Mode):
		self.Target_Temperature = int(targetTemp)
		self.Mode = Mode
		mode_file = open(self.__ModeFile,"w+")
		'''with open("thermostat.conf","w") as mode_file:'''
		mode_file.write("TargetTemperature=%s\n" % self.Target_Temperature)
		mode_file.write("Mode=" + self.Mode + "\n")
		mode_file.close()
		if self.__Immed_action or Mode=="OFF":
			self.Process()

	def Process(self):
		temp=self.Current_Temperature
		mode=self.Mode
		
		
		if self.Target_Temperature - temp > 3 and (mode == "HEAT" or mode=="AUTO"):
			# Set HEAT_2=ON, COOL=OFF
			GPIO.output([self.__HEAT_Pin,self.__HEAT2_Pin,self.__COOL_Pin],(GPIO.LOW, GPIO.LOW, GPIO.HIGH))
			return "ON"
		elif self.Target_Temperature - temp > 1 and (mode == "HEAT" or mode=="AUTO"):
			# Set HEAT_1=ON, COOL=OFF
			GPIO.output([self.__HEAT_Pin,self.__HEAT2_Pin,self.__COOL_Pin],(GPIO.LOW, GPIO.HIGH, GPIO.HIGH))
			return "ON"
		elif temp - self.Target_Temperature > 1 and (mode == "COOL" or mode=="AUTO"):
			# Process Cool Logic
			# Set HEAT=OFF, COOL=ON"
			GPIO.output([self.__HEAT_Pin,self.__HEAT2_Pin,self.__COOL_Pin],(GPIO.HIGH, GPIO.HIGH, GPIO.LOW))
			return "ON"
		else:
			GPIO.output([self.__HEAT_Pin,self.__HEAT2_Pin,self.__COOL_Pin],(GPIO.HIGH, GPIO.HIGH, GPIO.HIGH))
			return "OFF"
		GPIO.cleanup()
			
	




		


		









