import uuid
import hashlib
import json
import os
import sys
from  datetime import datetime, date
from bottle import response, request, redirect

import auth_pin


class auth_session:
	
	
	session_timeout = 20
	__session_data={}
	logout_redirect_url="/login"
	
	def __init__(self, **kwarg):
		self.save_session()
		return
		
	
	def save_session(self):
		with open(".session", "w+") as (sf):
			json.dump(self.__session_data,sf)
	
	
	def login(self, pin):
		pin_hash = hashlib.sha256(pin.encode()).hexdigest()
		if pin_hash == auth_pin.PIN_CODE:
			#create UUID
			sid = str(uuid.uuid1())
			dt = str (datetime.now())
			#create cookie
			response.set_cookie("sid",sid)
			#insert UUID:timestamp to .session file
			self.__session_data[sid]=dt
			self.save_session()
			return True
		else:
			return False
			
	@property
	def is_logged_in(self):
		#get cookie
		sid = request.get_cookie("sid")
		#read timestamp
		try:
			session_date = self.__session_data[sid]
		except KeyError:
			#redirect(self.logout_redirect_url)
			return False
		dt= datetime.strptime(session_date,'%Y-%m-%d %H:%M:%S.%f')
		if dt:
			date_diff = datetime.now()-dt
			session_age=(date_diff.days * 1440) + (date_diff.seconds/60) #convert days to minutes + convert seconds to minutes
			if session_age<self.session_timeout:
				return True
		self.logout()
		return False
	
	def logout(self):
		#get cookie
		sid = request.get_cookie("sid")
		del self.__session_data[sid]
		self.save_session()
		#redirect(self.logout_redirect_url)
		return 

def genhash(pin):
	APP_PATH = os.path.dirname(os.path.abspath(__file__))
	#print (pin)
	pinhash = hashlib.sha256(pin.encode()).hexdigest()
	print (pinhash)
	s = 'PIN_CODE = "' + pinhash + '"'
	with open(APP_PATH + "/auth_pin.py", "w+") as pin_code_file:
		pin_code_file.write(s)

if (__name__=="__main__"):
	if (len(sys.argv)>2):
		pin = sys.argv[2]
		if (sys.argv[1]=='genhash' and pin!=''):
			genhash(pin)
	else:
		print ("")
		print ("use genhash <pin> to generate/mofigy pin hash")


