import os, sys 

APP_PATH = os.path.dirname(os.path.abspath(__file__))

print (APP_PATH)
print (sys.path)

sys.path.append(APP_PATH)
os.chdir(os.path.dirname(__file__))

print (sys.path)

import bottle
import web
application=bottle.default_app()


