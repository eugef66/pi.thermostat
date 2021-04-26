import os
from bottle import route, run, template, static_file, redirect, request
import server  as s
import web_config as config


_login_url=config.WEBROOT + "/login"

APP_PATH = os.path.dirname(os.path.abspath(__file__))
os.environ['PYTHON_EGG_CACHE'] = '__pycache__'

def check_login():
	if (s.validate_login()):
		return True
	else:
		redirect (_login_url)
		return False



@route(config.WEBROOT + '/')
def index():
	if check_login():
		_response = s.get()
		
		print (_response)
		if (_response["Status"]):

			return template('index_template', Status=_response["Current_State"]
											, Current_Temperature=_response["Current_Temperature"]
											, Current_Humidity=_response["Current_Humidity"]
											, Target_Temperature=_response["Target_Temperature"]
											, Current_Mode=_response["Current_Mode"]
											, Stage=_response["Stage"]
											, Schedule=_response["Schedule"]
											,Web_Root = config.WEBROOT)
		else:
			return("error_template")

@route(config.WEBROOT + '/set/<mode>/<temp>')
def set(mode, temp):
	if check_login():
		schedule = request.GET.get('sch')
		if (len(schedule)>15):
			s.set(mode,temp, schedule)
		else:
			s.set(mode,temp)
		return redirect(config.WEBROOT + '/')

@route(config.WEBROOT + '/login')
def login():
	return template('login_template',Message=None)

@route(config.WEBROOT + '/login', method='POST')
def do_login():
	pin = request.forms.get('pin')
	if s.login(pin)["Status"]:
		redirect (config.WEBROOT + '/')
	else: 
		return template('login_template', Message='Login incorrect')



# static files
@route(config.WEBROOT + '/images/<filename>')
def images(filename):
	return static_file(filename, root= APP_PATH + '/images')

@route(config.WEBROOT + '/css/<filename>')
def css(filename):
	return static_file(filename, root=APP_PATH + '/css')

@route(config.WEBROOT + '/fonts/<filename>')
def css(filename):
	return static_file(filename, root=APP_PATH + '/fonts')

@route(config.WEBROOT + '/js/<filename>')
def css(filename):
	return static_file(filename, root=APP_PATH + '/js')

if __name__=='__main__':
	abspath = os.path.abspath(__file__)
	dname = os.path.dirname(abspath)
	os.chdir(dname)
	s.initialize()
	run(host='0.0.0.0', port=81)

