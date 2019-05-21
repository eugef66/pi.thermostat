from bottle import route, run, template, jinja2_template as template, static_file, redirect
import thermostat as th

@route('/')
def index():
	t=th.thermostat()
	ct,ch = t.Current_Temperature_Humidity
	return template('index_template', Status=t.Status, Current_Temperature=ct, Current_Humidity=ch, Color='blue',Target_Temperature=t.Target_Temperature, Current_Mode=t.Mode)

@route('/set/<mode>/<temp>')
def set(mode, temp):
	t=th.thermostat()
	t.Set(temp,mode)
	return redirect('/');

# static files
@route('/images/<filename>')
def server_static(filename):
	return static_file(filename, root='./images');


run(host='localhost', port=8888)
