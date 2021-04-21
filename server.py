import os
from bottle import route, run, request
import thermostat as th
import auth
import json


a=auth.auth_session()
a.logout_redirect_url="/login"

APP_PATH = os.path.dirname(os.path.abspath(__file__))
os.environ['PYTHON_EGG_CACHE'] = '__pycache__'



@route('/')
@route('/get')
@route('/get/all')
def get():
	_api_response={}
	if a.is_logged_in:	
		try:
			t=th.thermostat()
			ct,ch = t.Current_Temperature_Humidity
			s,st=t.Status
			_api_response["Status"]="OK"
			_api_response["Current_State"]=s
			_api_response["Current_Temperature"]=ct
			_api_response["Current_Humidity"]=ch
			_api_response["Target_Temperature"]=t.Target_Temperature
			_api_response["Current_Mode"]=t.Mode
			_api_response["Stage"]=st
			_api_response["Schedule"]=t.Schedule
		except Exception as e:
			_api_response["Status"] = "Error"
			_api_response["Error"] = e.args
	else:
		_api_response["Status"] = "Error"
		_api_response["Error"] = "Invalid Login"
	return _api_response


@route('/set/<mode>/<temp>')
def set(mode, temp):
	_api_response={}
	if a.is_logged_in:	
		try:
			schedule = request.GET.get('sch')
			t=th.thermostat()
			if (schedule != None and len(schedule)>15):
				t.Set(temp,mode,schedule)
			else:
				t.Set(temp,mode)
			_api_response["Status"]="OK"
		except Exception as e:
			_api_response["Status"] = "Error"
			_api_response["Error"] = e.args

	else:
		_api_response["Status"] = "Error"
		_api_response["Error"] = "Invalid Login"
	return _api_response


@route('/login', method='POST')
def login(pin = None):
	_api_response={}
	try:
		if (pin == None):
			pin = request.forms.get('pin')
		print ("pin:" + pin)
		if a.login(pin):
			_api_response["Status"]="OK"
		else: 
			_api_response["Status"] = "Error"
			_api_response["Error"] = "Invalid Login"
	except Exception as e:
		_api_response["Status"] = "Error"
		_api_response["Error"] = e.args
	finally:
		return _api_response

@route('/login/validate')
def validate_login():
	if a.is_logged_in:
		return {"Status":"OK"}
	else:
		return {"Status": "ERROR"}


if __name__=='__main__':
	abspath = os.path.abspath(__file__)
	dname = os.path.dirname(abspath)
	os.chdir(dname)
	t=th.thermostat()
	t.Initialize()
	run(host='0.0.0.0', port=81)

