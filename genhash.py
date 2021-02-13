import sys, hashlib

pin = sys.argv[1]
print (pin)
pinhash = hashlib.sha256(pin.encode()).hexdigest()
print (pinhash)