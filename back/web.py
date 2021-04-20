import os
from bottle import route, run, template, static_file, redirect, request
import thermostat as th
import auth #import auth_session


a=auth.auth_session()
a.logout_redirect_url="/login"

APP_PATH = os.path.dirname(os.path.abspath(__file__))
os.environ['PYTHON_EGG_CACHE'] = '__pycache__'




@route('/')
def index():
	if a.is_logged_in:
		_api_response={}
		t=th.thermostat()
		ct,ch = t.Current_Temperature_Humidity
		s,st=t.Status

		_api_response["Status"]=s
		_api_response["Current_Temperature"]=ct
		_api_response["Current_Humidity"]=ch
		_api_response["Target_Temperature"]=t.Target_Temperature
		_api_response["Current_Mode"]=t.Mode
		_api_response["Stage"]=st
		_api_response["Schedule"]=t.Schedule
		return _api_response

@route('/set/<mode>/<temp>')
def set(mode, temp):
	if a.is_logged_in:
		schedule = request.GET.get('sch')
		t=th.thermostat()
		if (len(schedule)>15):
			t.Set(temp,mode,schedule)
		else:
			t.Set(temp,mode)
		return redirect('/')

@route('/login')
def login():
	return template('front/login_template.html',Message=None)

@route('/login', method='POST')
def do_login():
	pin = request.forms.get('pin')
	if a.login(pin):
		redirect ('/')
	else: 
		return template('front/login_template.html', Message='Login incorrect')



# static files
@route('/images/<filename>')
def images(filename):
	return static_file(filename, root= APP_PATH + '/front/images')

@route('/css/<filename>')
def css(filename):
	return static_file(filename, root=APP_PATH + '/front/css')

@route('/fonts/<filename>')
def css(filename):
	return static_file(filename, root=APP_PATH + '/front/fonts')

@route('/js/<filename>')
def css(filename):
	return static_file(filename, root=APP_PATH + '/front/js')

if __name__=='__main__':
	abspath = os.path.abspath(__file__)
	dname = os.path.dirname(abspath)
	os.chdir(dname)
	t=th.thermostat()
	t.Initialize()
	run(host='0.0.0.0', port=81)

