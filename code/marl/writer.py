import csv
import errno    
import os

import numpy as np

# thanks, https://stackoverflow.com/questions/600268/
def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise

def writeResults(results_file, results, sarsa_dir=None, append=False, times_dir=None):
	(rewards, good_traffic_percents, total_loads, store_sarsas, rng_state, comp_times) = results

	mode = "a" if append else "w"

	# First, handle the actual results.
	pathy = os.path.split(results_file)
	mkdir_p(pathy[0])
	with open(results_file, mode) as csvfile:
		out = csv.writer(csvfile)
		all_t = 0
		# Key/headers
		if not append:
			out.writerow(["episode", "t", "global_t", "g_reward", "legit_traffic", "total_load"])
			
		for ep, (rewards_ep, g_traf_ep, load_ep) in enumerate(zip(rewards, good_traffic_percents, total_loads)):
			for t, (reward, g_traffic, load) in enumerate(zip(rewards_ep, g_traf_ep, load_ep)):
				out.writerow([ep, t, all_t, reward, g_traffic, load])
				all_t += 1

	# Okay, now output the sarsa learners' state.
	# Also, probably want to do something with rng state.
	if sarsa_dir is not None:
		# TODO
		pass

	# Stats about how long computation time takes (as a function of time...)
	if times_dir is not None:
		(notext, ext) = os.path.splitext(times_dir)
		times_avg_dir = "".join([notext, "-avg", ext])

		timeholder = {}
		with open(times_dir, mode) as csvfile:
			out = csv.writer(csvfile)
			for ep, data in enumerate(comp_times):
				for t, length in data:
					if t not in timeholder:
						timeholder[t] = []

					out.writerow([ep, t, length])
					timeholder[t].append(length)

		avgs = {}
		for t, lengths in timeholder.iteritems():
			avgs[t] = np.mean(np.array(lengths))

		with open(times_avg_dir, mode) as csvfile:
			out = csv.writer(csvfile)
			for t, cost in avgs.iteritems():
				out.writerow([t, cost])

def makeResultsAverage(in_path, out_path, drop_zeroes=False):
	with open(in_path, "r") as f_in:
		with open(out_path, "w") as f_out:
			c_in = csv.reader(f_in)
			c_out = csv.writer(f_out)

			# Headery stuff
			_ = c_in.next()
			c_out.writerow(["episode", "av_g_reward", "av_legit_traffic", "av_total_load"])

			stats = []

			for row in c_in:
				t = int(row[1])
				to_track = [float(x) for x in row[-3:]]
				# print row

				if len(stats) <= t:
					stats.append([[],[],[]])

				if drop_zeroes and to_track[-1]==0.0:
					continue;

				for target, entry in zip(stats[t], to_track):
					target.append(entry)

			# print stats

			for i, row in enumerate(stats):
				c_out.writerow([i] + [np.mean(np.array(c)) for c in row])

def lastTimestepsAndEpAverages(in_path, out_path):
	with open(in_path, "r") as f_in:
		with open(out_path, "w") as f_out:
			# assume it's in order. Take last timestamp for each episode.
			c_in = csv.reader(f_in)
			c_out = csv.writer(f_out)

			# Headery stuff
			_ = c_in.next()
			c_out.writerow(["episode", "g_reward", "legit_traffic", "total_load", "av_g_reward", "av_legit_traffic", "av_total_load"])

			lasts = []
			stats = []

			# May be the case that episode numbers are wrong
			# due to block-based writing/execution.
			# However, everything is still in chrono order.
			# Mitigate this by monitoring episode number
			# in case there's a sudden discontinuity, then fix.
			highest_ep = 0
			curr_seen = 0

			for row in c_in:
				seen_ep = int(row[0])
				
				if curr_seen != seen_ep:
					highest_ep += 1
				
				ep = highest_ep
				curr_seen = seen_ep

				t = int(row[1])
				to_track = [float(x) for x in row[-3:]]
				# print row

				if len(stats) <= ep:
					stats.append([[],[],[]])

				if len(lasts) <= ep:
					lasts.append([0.0, 0.0, 0.0])

				for target, entry in zip(stats[ep], to_track):
					target.append(entry)

				lasts[ep] = to_track

			# print stats

			for i, (s_row, l_row) in enumerate(zip(stats, lasts)):
				c_out.writerow([i] + l_row + [np.mean(np.array(c)) for c in s_row])

def dumbWriter(outDir, data):
	# honestly don't expect more than one level of depth here...
	if len(data) > 0 and isinstance(data[0], (list,)):
		true_dat = []
		for ep, data_ep in enumerate(data):
			for data_row in data_ep:
				true_dat.append([ep] + data_row)
	else:
		true_dat = data

	with open(outDir, "wb") as of:
		w = csv.writer(of)
		for row in true_dat:
			w.writerow(row)
