from bottle import route, run, template, jinja2_template as template, static_file, redirect, request
import thermostat as th
from auth import auth_session


a=auth_session()
a.redirect_url="/login"

@route('/')
def index():
	if a.is_logged_in:
		t=th.thermostat()
		ct,ch = t.Current_Temperature_Humidity
		return template('index_template', Status=t.Status, Current_Temperature=ct, Current_Humidity=ch, Color='blue',Target_Temperature=t.Target_Temperature, Current_Mode=t.Mode)

@route('/set/<mode>/<temp>')
def set(mode, temp):
	if a.is_logged_in:
		t=th.thermostat()
		t.Set(temp,mode)
		return redirect('/');

@route('/login')
def login():
	return template('login_template')

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
	return static_file(filename, root='./images');

@route('/css/<filename>')
def css(filename):
	return static_file(filename, root='./css');

@route('/fonts/<filename>')
def css(filename):
	return static_file(filename, root='./fonts');

@route('/js/<filename>')
def css(filename):
	return static_file(filename, root='./js');

print(__name__)

if __name__=='__main__':
	run(host='localhost', port=9998)
