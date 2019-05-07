import cPickle
from marl import *
import sys
from writer import writeResults, makeResultsAverage, dumbWriter

results_dir = "../../results/"

# prefix, spiffy_mode, discount
models = [
	"m", # MARL
	"mpp", # MARL++
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
	(2, 0.05),
	(4, 0.05),
	(8, 0.05),
	(16, 0.05),
]

# prefix, tcp?
traffic_types = [
	"tcp",
	"opus",
#	"mix",
]

# prefix, single_learner
single_learners = [
	("separate", False),
	("single", True),
]

topols = [
	"tree",
#	"ecmp",
]

def total_per_model(model):
	return len(discounts) * len(algos) * len(host_ps) * len(traffic_types) * (1 if model == 0 else len(single_learners)) * len(maths) * len(topols)

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
	# FIXME: do something with topol
	deps.append(topols)

	results = marlExperiment(**params)
	(rewards, good_traffic_percents, total_loads, store_sarsas, rng, action_comps) = results

	file_name_part = "tnsm-{}-{}-{}-{}-{}".format(topol, host_p, traffic_prefix, model_prefix, indiv_prefix)
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
