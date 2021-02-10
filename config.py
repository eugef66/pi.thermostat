import sys

# Uncomment the line below to use GPIO emulator and change path to emulators module
sys.path.append("../pi.emulators")

CALIBRATION=0
PERFORM_IMIDIATE_ACTION=True

# All PIN Numbers are BCM GPIO
HEAT_PIN = 2
HEAT_STAGE_2_PIN = 17
COOL_PIN = 3
COOL_STAGE_2_PIN = 18
SENSOR_PIN=4

#Enable for 2-stage systems
HEAT_TWO_STAGE=True
COOL_TWO_STAGE = False

