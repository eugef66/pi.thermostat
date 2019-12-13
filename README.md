# RPIThermostat
Python and PHP code for Raspberri PI based web-enabled thermostat

1. Hardware 

 - Raspberri PI 3B with power adapter 
 - DHT22 Themperature sensor - https://www.amazon.com/gp/product/B073F472JL
 - DC 5V Relay Module  - https://www.amazon.com/gp/product/B00E0NTPP4
 - Breadboard jumper wires (Female-Female) - https://www.amazon.com/gp/product/B07GD2BWPY

2. Software Prerequisite

  - Raspbian OS
  - Apache2 
  - Python 2.7

3. Installation instructions

 -------------set pins at boot
      sudo nano /etc/rc.local
      
            gpio -g write 2 1
            gpio -g write 3 1
            gpio -g write 17 1
            gpio -g mode 2 OUT
            gpio -g mode 3 OUT
            gpio -g mode 17 OUT
            
 


........

