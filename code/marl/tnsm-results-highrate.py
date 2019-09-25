import cPickle
from marl import *
import sys
from writer import writeResults, makeResultsAverage, dumbWriter

results_dir = "../../results/"

# prefix, spiffy_mode, discount
models = [
#	"m", # MARL
#	"spiffy", # Real SPIFFY
#	"mpp", # MARL++
	"spf", # SPF
]

# Use this to try out the effect of a sensible discount on Marl++...
discounts = [
	#0.0,
	0.8,
]
maths = [
	True,
#	False,
]

algos = [
	"sarsa",
#	"q",
]

# host_p, dt
host_ps = [
#	(2, 0.05),
#	(4, 0.05),
#	(8, 0.05),
	(16, 0.05),
]

# prefix, tcp?
traffic_types = [
	"tcp",
#	"opus",
#	"mix",
]

# prefix, single_learner
single_learners = [
#	("separate", False),
	("single", True),
]

topols = [
	"tree",
#	"ecmp",
]

evil_factors = [
	2.0,
	2.5,
	3.0,
	3.5,
]

def total_per_model(model):
	return len(evil_factors) * len(discounts) * len(algos) * len(host_ps) * len(traffic_types) * (1 if model < 2 else len(single_learners)) * len(maths) * len(topols)

if __name__ == "__main__":
	# If <2 args, return the upper bound of expts per model.
	if len(sys.argv) < 3:
		print total_per_model(int(sys.argv[1]))
		sys.exit(0)

	# if 2 args (both int), choose that model (0/1) and then that sub-experiment
	model = int(sys.argv[1])
	experiment = int(sys.argv[2])

	def expt_part(source, dependents=[]):
		fold_len = 1
		for el in dependents:
			fold_len *= len(el)
		return source[(experiment/fold_len) % len(source)]

	params = {
		#"P_good": 1.0,
		"n_teams": 2,
		"n_inters": 2,
		"n_learners": 3,

		"alpha": 0.05,
		"epsilon": 0.2,
		"discount": 0.0,
		"dt": 0.05,

		"ecmp_servers": 2,

		"explore_episodes": 0.8,
		"episodes": 10,
		"episode_length": 10000,
		"separate_episodes": True,

		"rf": "marl",
		"use_controller": True,
		"actions_target_flows": True,
		"trs_maxtime": 0.001,

		"split_codings": True,
		"feature_max": 20,
	}

	deps = []

	discount = expt_part(discounts, deps)
	deps.append(discounts)

	# model stuff
	model_prefix = models[model]
	old_marl = False
	if model_prefix == "m":
		# Old, original marl.
		old_marl = True
		params["rf"] = "ctl"
		params["epsilon"] = 0.2
		params["explore_episodes"] = 0.3
		del params["actions_target_flows"]
		del params["feature_max"]
		del params["split_codings"]
		del params["trs_maxtime"]
	elif model_prefix == "spiffy":
		old_marl = True
		params["spiffy_but_bad"] = True
		params["spiffy_act_time"] = 5.0
		params["spiffy_max_experiments"] = 16
		params["spiffy_min_experiments"] = 16
		params["spiffy_pick_prob"] = 0.1
		params["spiffy_traffic_dir"] = "in"
		params["spiffy_mbps_cutoff"] = 0.01
		params["spiffy_expansion_factor"] = 3.0
	elif model_prefix == "mpp":
		pass
	elif model_prefix == "spf":
		params["spiffy_mode"] = True
		params["discount"] = discount

	# host count stuff.
	(host_p, dt) = expt_part(host_ps, deps)
	params["host_range"] = [host_p, host_p]
	params["dt"] = dt
	deps.append(host_ps)

	# Traffic model stuff
	traffic_prefix = expt_part(traffic_types, deps)
	if traffic_prefix == "tcp":
		params["model"] = "nginx"
		params["randomise"] = True
		params["randomise_count"] = 1
		params["randomise_new_ip"] = True
		params["reward_direction"] = "out"
		params["evil_range"] = [4, 7]
	elif traffic_prefix == "udp":
		params["model"] = "nginx"
		params["submodel"] = "udp-flood"
		params["reward_direction"] = "in"
	elif traffic_prefix == "opus":
		params["model"] = "nginx"
		params["submodel"] = "opus-voip"
		params["randomise"] = True
		params["randomise_new_ip"] = True
		params["reward_direction"] = "in"
	elif traffic_prefix == "mix":
		params["randomise"] = True
		params["randomise_count"] = 1
		params["randomise_new_ip"] = True
		params["reward_direction"] = "inout"
		params["mix_model"] = [
			# TCP
			(0.8, {
				"model": "nginx",
				"submodel": None
			}),
			# Opus
			(0.2, {
				"model": "nginx",
				"submodel": "opus-voip",
			}),
		]
	deps.append(traffic_types)

	broken_math = expt_part(maths, deps)
	params["broken_math"] = broken_math
	deps.append(maths)

	algo = expt_part(algos, deps)
	params["algo"] = algo
	deps.append(algos)

	params["estimate_const_limit"] = True
	if not old_marl:
		(indiv_prefix, single_learner) = expt_part(single_learners, deps)
		params["single_learner"] = single_learner
		deps.append(single_learners)
	else:
		indiv_prefix = "separate"

	topol = expt_part(topols, deps)
	params["topol"] = topol
	deps.append(topols)

	if model_prefix == "spiffy":
		spiffy_count = int(0.1 * float(host_p * 12))
		if topol == "ecmp":
			spiffy_count *= 3
		params["spiffy_max_experiments"] = spiffy_count
		params["spiffy_min_experiments"] = spiffy_count

	ef = expt_part(evil_factors, deps)
	params["evil_range"] = [x * ef for x in params["evil_range"]]
	deps.append(evil_factors)

	results = marlExperiment(**params)
	(rewards, good_traffic_percents, total_loads, store_sarsas, rng, action_comps) = results

	file_name_part = "tnsm-highrate-{}".format(ef)
	file_name = file_name_part + ".csv"
	file_name_avg = file_name_part + ".avg.csv"
	file_name_sarsas = file_name_part + ".pickle"
	file_name_deltas = file_name_part + ".deltas.csv"

	csv_dir = results_dir + file_name
	avg_csv_dir = results_dir + file_name_avg
	sarsas_dir = results_dir + file_name_sarsas
	deltas_dir = results_dir + file_name_deltas

	writeResults(csv_dir, results)
	makeResultsAverage(csv_dir, avg_csv_dir)
	dumbWriter(deltas_dir, action_comps)
	with open(sarsas_dir, "wb") as f:
		cPickle.dump(store_sarsas, f)
	print "{} would write to: {}".format(experiment, csv_dir)
