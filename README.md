# pi.thermostat
Python and PHP code for Raspberri PI based web-enabled thermostat. 
 - Can run in standalone mode using bottle python web framework. 
 - Standalone server-only mode to provide API for third-party clients (web, app, IoTs, etc)
 - Can be deployed on more robust web server such as Apache, Lighttpd or other web servers which supports WSGI. Can be deployed with UI or in sevrer-only mode.

## 1. Hardware 

 - Raspberri PI 3B with power adapter 
 - DHT22 Themperature sensor - https://www.amazon.com/gp/product/B073F472JL
 - DC 5V Relay Module  - https://www.amazon.com/gp/product/B07YRYBLSZ
 - Breadboard jumper wires (Female-Female) - https://www.amazon.com/gp/product/B07GD2BWPY

## 2. Software Prerequisite

  - Raspbian OS
  - Apache2 
  - Python 2.7 (tested on 2.7.16, but should work with Python3)
  - RPi.GPIO Python module (https://pypi.org/project/RPi.GPIO/)
  - Adafruit_DHT Python module (https://github.com/adafruit/Adafruit_Python_DHT) 
  - (optional) WiringPi (http://wiringpi.com/) - comes PRE-INSTALLED with standard Raspbian desktop system. 
             For "Raspbery OS Lite" install using "sudo apt install wiringpi"
  

## 3. Installation instructions

 ### Gernerate pin code hash
	python auth.py genhash "pin code"
example: 
	
	python auth.py genhash 1111

 ### Create cron job 
 	sudo crontab -e 
add following command. Replace "app directory" with your working directory
	
	* * * * * python "app directory"/proc.py >> "app directory"/proc.log 2>&1
 
 ### Standalone:
 This installation allows you to run thermostat using included "bottle" web server and doesn't require Apache, Lighttpd or other web servers installed. It is single-threaded and slow, but a good choice for a simple and quick setup if light use is excpected. 

#### 1. Initialize GPIO on startup and start bottle web server

	sudo nano /etc/rc.local

##### with UI 
add following command before `exit(0)`

	python "app directroy"/client.py >> <app directory>/web.log 2>&1

##### standalone SERVER-ONLY 
	
	python "app directroy"/server.py >> <app directory>/web.log 2>&1

restart RPI

	sudo reboot 

### Advanced (with Apache2 server):
This installation allows you to run thermostat with Apache, Lighttpd or other web servers which supports WSGI. 
#### 1. Initialize GPIO on startup

	sudo nano /etc/rc.local

add following command before `exit(0)`

	python <APP DIRECTORY>/thermostat.py init >> <APP DIRECTORY>/thermostat.log 2>&1

Also, make sure user that user account Apache server is running as (usualy www-data) is added to gpio group

	sudo usermod -aG gpio www-data 


#### 2. Configure WSGI on Apache2 sevrer
Install WSGI module for Apcahe2

	 sudo apt install libapache2-mod-wsgi

Make sure WSGI mode is enabled

	sudo a2enmod wsgi

#### 3. Configure Apache2 
Create thermostat.conf file at /etc/apache2/sites-available and add following configuration (repalce application path and port to the one you use)

	<VirtualHost *:81>
        ServerName pi.thermostat.rpi3b.local
        ServerAdmin admin@localhost

        DocumentRoot /home/pi/apps/pi.thermostat
        ErrorLog /home/pi/apps/apache_error_81.log
        CustomLog /home/pi/apps/apache_access_81.log combined

        WSGIDaemonProcess pi.thermostat user=www-data group=www-data processes=1 threads=5
        WSGIScriptAlias / /home/pi/apps/pi.thermostat/app.wsgi

		<Directory /home/pi/apps/pi.thermostat>
			WSGIProcessGroup pi.thermostat
			WSGIApplicationGroup %{GLOBAL}
			Order deny,allow
			Allow from all
			Options Indexes FollowSymLinks
			AllowOverride All
			Require all granted
		</Directory>
	</VirtualHost>


Enable thermostat web site

	sudo a2ensite thermostat
    
            
 




