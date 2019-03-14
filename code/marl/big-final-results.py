import cPickle
from marl import *
import sys
from writer import writeResults, makeResultsAverage

results_dir = "../../results/"

# prefix, spiffy_mode, discount
models = [
	("m", False, 0.0), # MARL
	("spf", True, 0.8), # SPF
]

# host_p, dt
host_ps = [
	(2, 0.05),
	(4, 0.05),
	(8, 0.05),
	(16, 0.05)
]

# prefix, tcp?
traffic_types = [
	("udp", False),
	("tcp", True),
]

# prefix, reward_band, estimate_const_limit,
reward_bands = [
	("uncap", 1.0, False),
	("natural", 1.0, True),
	("banded", 0.99, True),
]

# prefix, single_learner
single_learners = [
	("separate", False),
	("single", True),
]

total_per_model = len(host_ps) * len(traffic_types) * (len(single_learners) + len(reward_bands))
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
	reward_index = None if indiv >= len(reward_bands) else indiv
	single_index = None if indiv < len(reward_bands) else indiv - len(reward_bands)

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
		"episode_length": 10000,
		"separate_episodes": True,

		"rf": "ctl",
		"use_controller": True,
		"actions_target_flows": True,
		"trs_maxtime": 0.001,

		"split_codings": True,
		"feature_max": 18,

		"broken_math": True,
	}

	# model stuff
	(model_prefix, spiffy_mode, discount) = models[model]
	params["spiffy_mode"] = spiffy_mode
	params["discount"] = discount

	# host count stuff.
	(host_p, dt) = host_ps[host_index]
	params["host_range"] = [host_p, host_p]
	params["dt"] = dt

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

	# indiv stuff
	if reward_index is not None:
		(indiv_prefix, reward_band, estimate_const_limit) = reward_bands[reward_index]
		params["reward_band"] = reward_band
		params["estimate_const_limit"] = estimate_const_limit

	if single_index is not None:
		(indiv_prefix, single_learner) = single_learners[single_index]
		params["single_learner"] = single_learner
		params["estimate_const_limit"] = True

	results = marlExperiment(**params)
	(rewards, good_traffic_percents, total_loads, store_sarsas, rng, action_comps) = results

	file_name_part = "{}-{}-{}-{}".format(model_prefix, traffic_prefix, indiv_prefix, host_p)
	file_name = file_name_part + ".csv"
	file_name_avg = file_name_part + ".avg.csv"
	sarsas_file = file_name_part + ".pickle"

	csv_dir = results_dir + file_name
	avg_csv_dir = results_dir + file_name_avg
	sarsas_dir = results_dir + sarsas_file

	writeResults(csv_dir, results)
	makeResultsAverage(csv_dir, avg_csv_dir)
	with open(sarsas_dir, "wb") as f:
		cPickle.dump(store_sarsas, f)
	print "would write to: {}".format(csv_dir)
