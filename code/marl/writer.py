import csv
import errno    
import os

# thanks, https://stackoverflow.com/questions/600268/
def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise

def writeResults(results_file, results, sarsa_dir=None):
	(rewards, good_traffic_percents, total_loads, store_sarsas) = results

	# First, handle the actual results.
	mkdir_p(os.path.split(results_file)[0])
	with open(results_file, "w") as csvfile:
		out = csv.writer(csvfile)
		all_t = 0
		# Key/headers
		out.writerow(["episode", "t", "global_t", "g_reward", "legit_traffic", "total_load"])
		for ep, (rewards_ep, g_traf_ep, load_ep) in enumerate(zip(rewards, good_traffic_percents, total_loads)):
			for t, (reward, g_traffic, load) in enumerate(zip(rewards_ep, g_traf_ep, load_ep)):
				out.writerow([ep, t, all_t, reward, g_traffic, load])
				all_t += 1

	# Okay, now output the sarsa learners' state.
	if sarsa_dir is not None:
		pass
