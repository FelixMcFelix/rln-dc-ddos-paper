from marl import *
from writer import writeResults, makeResultsAverage, lastTimestepsAndEpAverages
import subprocess
import cPickle

pickle_name = "../../results/offline.pkl"
total_eps = 10000#0
block_size = 50

# Create the file
writeResults("../../results/offline.csv", ([], [], [], [], None))

# Run these, natch into sets of 50.
for i in xrange(0, total_eps, block_size):
	remaining = total_eps - i
	local_block = block_size if remaining >= block_size else remaining
	subprocess.call(["python", "offline-internal.py", pickle_name, str(local_block), str(total_eps), str(int(i != 0))])

# Combine final results.
lastTimestepsAndEpAverages("../../results/offline.csv", "../../results/offline-avg.csv")
