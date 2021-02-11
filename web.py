import os
from bottle import route, run, template, static_file, redirect, request
import thermostat as th
from auth import auth_session


a=auth_session()
a.logout_redirect_url="/login"

APP_PATH = os.path.dirname(os.path.abspath(__file__))

@route('/')
def index():
	if a.is_logged_in:
		t=th.thermostat()
		ct,ch = t.Current_Temperature_Humidity
		s,st=t.Status
		return template('index_template', Status=s, Current_Temperature=ct, Current_Humidity=ch, Color='blue',Target_Temperature=t.Target_Temperature, Current_Mode=t.Mode, Stage=st)

@route('/set/<mode>/<temp>')
def set(mode, temp):
	if a.is_logged_in:
		t=th.thermostat()
		t.Set(temp,mode)
		return redirect('/')

@route('/login')
def login():
	return template('login_template',Message=None)

@route('/login', method='POST')
def do_login():
	pin = request.forms.get('pin')
	if a.login(pin):
		redirect ('/')
	else: 
		return template('login_template', Message='Login incorrect')



# static files
@route('/images/<filename>')
def images(filename):
	return static_file(filename, root= APP_PATH + '/images')

@route('/css/<filename>')
def css(filename):
	return static_file(filename, root=APP_PATH + '/css')

@route('/fonts/<filename>')
def css(filename):
	return static_file(filename, root=APP_PATH + '/fonts')

@route('/js/<filename>')
def css(filename):
	return static_file(filename, root=APP_PATH + '/js')

#print(__name__)

if __name__=='__main__':
	run(host='localhost', port=9988)
