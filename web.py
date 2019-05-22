from bottle import route, run, template, jinja2_template as template, static_file, redirect, request
import hashlib
from  datetime import datetime, date
import thermostat as th

def checkLogin():
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
		redirect('/login')


@route('/')
def index():
	if checkLogin()==True:
		t=th.thermostat()
		ct,ch = t.Current_Temperature_Humidity
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
	#print (pin_hash)
	if pin_hash == '1b8ba0b107410f67c70ab6ed4abf4e0ec0e70df78298e41d1670c7c1e94a703f':
		start_session()
		redirect ('/')
	else: 
		# destroy session
		return template('login_template', Message='Login incorrect')

def start_session():
	#Update to handle multiple browsers
	session_file = open(".session","w+t")
	session_file.write(str(datetime.now()))
	session_file.close()
	return

def destroy_session():
	session_file = open(".session","w+t")
	session_file.write("")
	session_file.close()
	return

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
