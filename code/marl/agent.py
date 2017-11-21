import sys
import subprocess
import time
import random

def agent(id, bwlimit):
	time.sleep(0.5 + random.random())
	print "Agent {} reporting for duty!".format(id)
	# sys.cmd("touch", "s{}.txt".format(id))
	print subprocess.check_output(["ethstats"])

if __name__ == '__main__':
	agent(int(sys.argv[1]), int(sys.argv[2]))