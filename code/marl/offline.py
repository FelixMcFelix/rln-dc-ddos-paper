from marl import *
from writer import writeResults, makeResultsAverage, lastTimestepsAndEpAverages
import subprocess
import cPickle

pickle_name = "../../results/offline.pkl"
total_eps = 10000#0
block_size = 50

for i in xrange(0, total_eps, block_size):
	remaining = total_eps - i
	local_block = block_size if remaining >= block_size else remaining
	subprocess.call(["python", "offline-internal.py", pickle_name, str(local_block), str(int(i != 0))])

# process data from loaded pickle
with open(pickle_name, "rb") as in_file:
	results = cPickle.load(in_file)

writeResults("../../results/offline.csv", results)
lastTimestepsAndEpAverages("../../results/offline.csv", "../../results/offline-avg.csv")
