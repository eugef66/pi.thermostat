import sys

# Uncomment the line below to use GPIO emulator and change path to emulators module
sys.path.append("../pi.emulators")



CALIBRATION=0
PERFORM_IMIDIATE_ACTION=True

# All PIN Numbers are BCM GPIO
SENSOR_PIN=4
HEAT_PIN = 2
COOL_PIN = 3

#Support for 2 stage systems
HEAT_TWO_STAGE=True
HEAT_STAGE_2_PIN = 17

COOL_TWO_STAGE = False
COOL_STAGE_2_PIN = 18
