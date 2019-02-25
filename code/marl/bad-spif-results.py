import cPickle
from marl import *
import sys
from writer import writeResults, makeResultsAverage

results_dir = "../../results/"

# prefix, spiffy_mode, discount
models = [
	("spiffy", True), # Poor man's SPIFFY
]

# host_p, dt
host_ps = [(2, 0.05), (4, 0.05), (8, 0.05), (16, 0.05)]

# prefix, tcp?
traffic_types = [
	("udp", False),
	("tcp", True),
]

total_per_model = len(host_ps) * len(traffic_types)
host_step = total_per_model / len(host_ps)
traffic_step = host_step / len(traffic_types)

if __name__ == "__main__":
	# If <2 args, return the upper bound of expts per model.
	if len(sys.argv) < 3:
		print total_per_model
		sys.exit(0)

	# if 2 args (both int), choose that model (0/1) and then that sub-experiment
	model = int(sys.argv[1])
	experiment = int(sys.argv[2])

	host_index = experiment / host_step
	traffic_index = (experiment / traffic_step) % 2

	indiv = experiment % (traffic_step)

	params = {
		"n_teams": 2,
		"n_inters": 2,
		"n_learners": 3,

		"alpha": 0.05,
		"epsilon": 0.2,
		"discount": 0.0,
		"dt": 0.05,

		"explore_episodes": 0.8,
		"episodes": 10,
		"episode_length": 3000,
		"separate_episodes": True,

		"rf": "ctl",
		"use_controller": True,
		"actions_target_flows": True,
		"trs_maxtime": 0.001,

		"split_codings": True,
		"feature_max": 18,
	}

	# model stuff
	(model_prefix, bad_mode) = models[model]
	params["spiffy_but_bad"] = bad_mode

	# host count stuff.
	(host_p, dt) = host_ps[host_index]
	params["host_range"] = [host_p, host_p]
	params["dt"] = dt

	# rate-limiting
	params["estimate_const_limit"] = True

	# Traffic model stuff
	(traffic_prefix, is_tcp) = traffic_types[traffic_index]
	if is_tcp:
		params["model"] = "nginx"
		params["randomise"] = True
		params["randomise_count"] = 1
		params["randomise_new_ip"] = True
		params["reward_direction"] = "out"
		params["evil_range"] = [4, 7]
		#params["use_controller"] = True
	else:
		params["model"] = "nginx"
		params["submodel"] = "udp-flood"
		#params["use_controller"] = False
		pass

	results = marlExperiment(**params)

	file_name_part = "{}-{}-{}".format(model_prefix, traffic_prefix, host_p)
	file_name = file_name_part + ".csv"
	file_name_avg = file_name_part + "-avg.csv"

	csv_dir = results_dir + file_name
	avg_csv_dir = results_dir + file_name_avg

	writeResults(csv_dir, results)
	makeResultsAverage(csv_dir, avg_csv_dir)
	#print "would write to: {}".format(csv_dir)
