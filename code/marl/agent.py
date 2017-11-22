import sys
import subprocess
import time
import random
import re

def arrify(string):
	return [x.strip().split() for x in string.splitlines()]

def agent(id, bwlimit):
	bw_kbps = bwlimit*1000

	# We want to test DURING e.g., iperf. So sleep!
	time.sleep(0.5 + random.random())

	# Sanity check.
	print "Agent {} reporting for duty!".format(id)

	# Read in net stats from OS. Split by lines, then by whitespace.
	stats = arrify(subprocess.check_output(["ifstat", "-nbT", "0.1", "1"]))

	# Last line has the numbers we want.
	# Convert as needed into floats, organise as in/out pairs and then convert to frac.
	last_line = [float(x) for x in stats[-1]]
	statpairs = zip(last_line[::2], last_line[1::2])
	stat_frac = [(l*100/bw_kbps, r*100/bw_kbps) for (l, r) in statpairs]

	# Grab any relevant interfaces, print their stats.
	ifs = []
	for i, el in enumerate(stats[0]):
		if "s{}-".format(id) in el:
			ifs.append((i, el))
			print "{0} utilisation: in {2:.2f}%, out {3:.2f}% ({1:.2f} Mbps)".format(
				el, bwlimit, *stat_frac[i]
			)

	# And now you know how to do it for real!


if __name__ == '__main__':
	agent(int(sys.argv[1]), float(sys.argv[2]))