import os
import math
def get_cpu_temp():
	with os.popen('cat /sys/class/thermal/thermal_zone0/temp') as temp_file:
		temp_str = temp_file.read().strip()
		
		temp_c = float(temp_str) / 1000.0
		temp_c = int(math.ceil(temp_c))
		return temp_c
