from bottle import route, run, template, jinja2_template as template
import thermostat as th

@route('/')
def index():
	t=th.thermostat()
	ct,ch = t.Current_Temperature_Humidity
	return template('index_template', Status=t.Status, Current_Temperature=ct, Current_Humidity=ch, Color='blue',Target_Temperature=t.Target_Temperature, Current_Mode=t.Mode)

def set(mode, temp):
	t=th.thermostat()
	t.Set(temp,mode)

run(host='localhost', port=8888)
