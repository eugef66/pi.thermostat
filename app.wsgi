import os, sys 
sys.path = ['/home/pi/Apps/Thermostat/'] + sys.path
os.chdir(os.path.dirname(__file__))

import bottle
import web
application=bottle.default_app()


#def application(environ, start_response):
#    status = '200 OK'
#    output = str(sys.path)
#    response_headers = [('Content-type', 'text/plain'),
#                        ('Content-Length', str(len(output)))]
#    start_response(status, response_headers)

#    return [output]