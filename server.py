import os
from bottle import route, run, request
import thermostat as th
import web_config as config
import auth
import json


a = auth.auth_session()


APP_PATH = os.path.dirname(os.path.abspath(__file__))
os.environ['PYTHON_EGG_CACHE'] = '__pycache__'


def initialize():
    t = th.thermostat()
    t.Initialize()


@route(config.WEBROOT + '/')
@route(config.WEBROOT + '/get')
@route(config.WEBROOT + '/get/all')
def get():
    _api_response = {}
    if a.is_logged_in:
        try:
            t = th.thermostat()
            ct, ch = t.Current_Temperature_Humidity
            s, st = t.Status
            _api_response["Status"] = True
            _api_response["Current_State"] = s
            _api_response["Current_Temperature"] = ct
            _api_response["Current_Humidity"] = ch
            _api_response["Target_Temperature"] = t.Target_Temperature
            _api_response["Current_Mode"] = t.Mode
            _api_response["Stage"] = st
            _api_response["Schedule"] = t.Schedule
        except Exception as e:
            _api_response["Status"] = False
            _api_response["Error"] = e.args
    else:
        _api_response["Status"] = False
        _api_response["Error"] = "Invalid Login"
    return _api_response


@route(config.WEBROOT + '/set/<mode>/<temp>')
def set(mode, temp, schedule=None):
    _api_response = {}
    if a.is_logged_in:
        try:
            if (schedule == None):
                schedule = request.GET.get('sch')
            t = th.thermostat()
            if (schedule != None and len(schedule) > 15):
                t.Set(temp, mode, schedule)
            else:
                t.Set(temp, mode)
            _api_response["Status"] = True
        except Exception as e:
            _api_response["Status"] = False
            _api_response["Error"] = e.args
    else:
        _api_response["Status"] = False
        _api_response["Error"] = "Invalid Login"
    return _api_response


@route(config.WEBROOT + '/login', method='POST')
def login(pin=None):
    _api_response = {}
    try:
        if (pin == None):
            pin = request.forms.get('pin')
        if (a.login(pin)):
            _api_response["Status"] = True
        else:
            _api_response["Status"] = False
            _api_response["Error"] = "Invalid Login"
    except Exception as e:
        _api_response["Status"] = False
        _api_response["Error"] = e.args
    return _api_response


@route(config.WEBROOT + '/login/validate')
def validate_login():
    return a.is_logged_in


if __name__ == '__main__':
    abspath = os.path.abspath(__file__)
    dname = os.path.dirname(abspath)
    os.chdir(dname)
    t = th.thermostat()
    t.Initialize()
    run(host='0.0.0.0', port=81)
