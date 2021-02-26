# pi.thermostat
Python and PHP code for Raspberri PI based web-enabled thermostat

## 1. Hardware 

 - Raspberri PI 3B with power adapter 
 - DHT22 Themperature sensor - https://www.amazon.com/gp/product/B073F472JL
 - DC 5V Relay Module  - https://www.amazon.com/gp/product/B07YRYBLSZ
 - Breadboard jumper wires (Female-Female) - https://www.amazon.com/gp/product/B07GD2BWPY

## 2. Software Prerequisite

  - Raspbian OS
  - Apache2 
  - Python 2.7 (tested on 2.7.16, but should work with Python3)
  - WiringPi (http://wiringpi.com/) - comes PRE-INSTALLED with standard Raspbian desktop system. 
             For "Raspbery OS Lite" install using "sudo apt install wiringpi"
  - RPi.GPIO Python module (https://pypi.org/project/RPi.GPIO/)
  - Adafruit_DHT Python module (https://github.com/adafruit/Adafruit_Python_DHT) 

## 3. Installation instructions

 ### Gernerate pin code hash
	python auth.py genhash "pin code"
example: 
	
	python auth.py genhash 1111

 ### Create cron job 
 	sudo crontab -e 
add following command. Replace "app directory" with your working directory
	
	* * * * * python "app directory"/proc.py >> "app directory"/proc.log 2>&1
 
 ### Simple self-running (no Apache):
This installation allows you to run thermostat using included "bottle" web server and doesn't require Apache, Lighttpd or other web servers installed. It is single-threaded and slow, but a good choice for a simple and quick setup if light use is excpected. 

	sudo nano /etc/rc.local
add following command before `exit(0)`

	python "app directroy"/startup.py >> "app directory"/app.log 2>&1
 
 ### Advanced (with Apache2 server):
  
  1. set default state of pins at boot
      - sudo nano /etc/rc.local
      
            gpio -g write 2 1
            gpio -g write 3 1
            gpio -g write 17 1
            gpio -g mode 2 OUT
            gpio -g mode 3 OUT
            gpio -g mode 17 OUT
            
 




