import os
from bottle import route, run, template, static_file, redirect, request
from server import get, login, set, validate_login


__logout_redirect_url="/login"

APP_PATH = os.path.dirname(os.path.abspath(__file__))
os.environ['PYTHON_EGG_CACHE'] = '__pycache__'

def check_login():
	if (s.validate_login()):
		return True
	else:
		return template('login_template')



@route('/')
def index():
	if check_login():
		t=th.thermostat()
		ct,ch = t.Current_Temperature_Humidity
		s,st=t.Status
		return template('index_template', Status=s
										, Current_Temperature=ct
										, Current_Humidity=ch
										, Target_Temperature=t.Target_Temperature
										, Current_Mode=t.Mode
										, Stage=st
										, Schedule=t.Schedule)

@route('/set/<mode>/<temp>')
def set(mode, temp):
	if check_login():
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
	if s.login():
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

