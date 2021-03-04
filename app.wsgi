import os, sys 

APP_PATH = os.path.dirname(os.path.abspath(__file__))

sys.path.append(APP_PATH)
os.chdir(os.path.dirname(__file__))

import bottle
import web
application=bottle.default_app()


