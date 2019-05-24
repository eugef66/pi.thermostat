import uuid
import hashlib
import json
from  datetime import datetime, date
from bottle import response, request, redirect


class auth_session:
	
	session_timeout = 20
	__session_data={}
	redirect_url="/login"
	
	def __init__(self, **kwarg):
		self.save_session()
		return
		
	
	def save_session(self):
		with open(".session", "w+") as (sf):
			json.dump(self.__session_data,sf)
	
	
	def login(self, pin):
		pin_hash = hashlib.sha256(pin.encode()).hexdigest()
		if pin_hash == '1b8ba0b107410f67c70ab6ed4abf4e0ec0e70df78298e41d1670c7c1e94a703f':
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
			redirect(self.redirect_url)
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
		redirect(self.redirect_url)
		return 
		



	def checkLogin(self):
		# Update to handle miltiple browsers
		session_timeout = 20
		valid=False
		session_age= session_timeout+1
		try:
			sf = open (".session","r")
			session_date=datetime.strptime(sf.read(), '%Y-%m-%d %H:%M:%S.%f')
			sf.close()
			if session_date:
				session_age=((datetime.now()-session_date).seconds/60)
		except IOError:
			pass
		print (session_age)
		if session_age<session_timeout:
			return True
		else:
			redirect('./login')

