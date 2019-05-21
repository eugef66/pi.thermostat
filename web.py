from bottle import route, run, template, jinja2_template as template, static_file, redirect, request
import hashlib
import datetime
import thermostat as th

def checkLogin():
	#check session
	valid=True
	if valid==True:
		return True
	else:
		redirect('/login')


@route('/')
def index():
	if checkLogin()==True:
		t=th.thermostat()
		print (datetime.datetime.now().time())
		ct,ch = t.Current_Temperature_Humidity
		print (datetime.datetime.now().time())
		return template('index_template', Status=t.Status, Current_Temperature=ct, Current_Humidity=ch, Color='blue',Target_Temperature=t.Target_Temperature, Current_Mode=t.Mode)

@route('/set/<mode>/<temp>')
def set(mode, temp):
	if checkLogin()==True:
		t=th.thermostat()
		t.Set(temp,mode)
		return redirect('/');

@route('/login')
def login():
	return template('login_template')

@route('/login', method='POST')
def do_login():
	pin = request.forms.get('pin')
	pin_hash = hashlib.sha256(pin.encode()).hexdigest()
	print (pin_hash)
	if pin_hash == '1b8ba0b107410f67c70ab6ed4abf4e0ec0e70df78298e41d1670c7c1e94a703f':
		# start session
		redirect ('/')
	else: 
		# destroy session
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


if __name__=='__main__':
	run(host='localhost', port=8888)
