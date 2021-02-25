import sys, hashlib, os

APP_PATH = os.path.dirname(os.path.abspath(__file__))

pin = sys.argv[1]
#print (pin)
pinhash = hashlib.sha256(pin.encode()).hexdigest()
print (pinhash)

s = 'PIN_CODE = "' + pinhash + '"'

with open(APP_PATH + "/auth_pin.py", "w+") as pin_code_file:
	pin_code_file.write(s)
