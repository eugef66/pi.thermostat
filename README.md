# pi.thermostat
Python and PHP code for Raspberri PI based web-enabled thermostat

1. Hardware 

 - Raspberri PI 3B with power adapter 
 - DHT22 Themperature sensor - https://www.amazon.com/gp/product/B073F472JL
 - DC 5V Relay Module  - https://www.amazon.com/gp/product/B07YRYBLSZ
 - Breadboard jumper wires (Female-Female) - https://www.amazon.com/gp/product/B07GD2BWPY

2. Software Prerequisite

  - Raspbian OS
  - Apache2 
  - Python 2.7 (tested on 2.7.16, but should work with Python3)
  - WiringPi (http://wiringpi.com/) - comes PRE-INSTALLED with standard Raspbian desktop system. 
             For "Raspbery OS Lite" install using "sudo apt install wiringpi"
  - RPi.GPIO Python module (https://pypi.org/project/RPi.GPIO/)
  - Adafruit_DHT Python module (https://github.com/adafruit/Adafruit_Python_DHT) 

3. Installation instructions

 - Simple self-running (no Apache)
 - 
 - Advanced with Apache2 server 
  
  1. set default state of pins at boot
      - sudo nano /etc/rc.local
      
            gpio -g write 2 1
            gpio -g write 3 1
            gpio -g write 17 1
            gpio -g mode 2 OUT
            gpio -g mode 3 OUT
            gpio -g mode 17 OUT
            
 




