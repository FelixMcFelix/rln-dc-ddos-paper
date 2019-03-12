import cPickle
from marl import *
import sys
from writer import writeResults, makeResultsAverage, dumbWriter

results_dir = "../../results/"

# prefix, spiffy_mode, discount
models = [
#	("m", False), # MARL
	("spf", True), # SPF
]

# Use this to try out the effect of a sensible discount on Marl++...
discounts = [
	#0.0,
	0.8,
]
maths = [
	True,
	False,
]

algos = [
	"sarsa",
#	"q",
]

# host_p, dt
host_ps = [(16, 0.05)]

# prefix, tcp?
traffic_types = [
#	("udp", False),
	("tcp", True),
]

# prefix, single_learner
single_learners = [
#	("separate", False),
	("single", True),
]

# prefix, record_deltas_in_times
measures = [
	("", False),
	("-observed", True),
]

total_per_model = len(discounts) * len(algos) * len(host_ps) * len(traffic_types) * len(single_learners) * len(maths) * len(measures)

if __name__ == "__main__":
	# If <2 args, return the upper bound of expts per model.
	if len(sys.argv) < 3:
		print total_per_model
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
		#"episodes": 2,
		"episode_length": 30000,
		#"episode_length": 30,
		"separate_episodes": True,

		"rf": "ctl",
		"use_controller": True,
		"actions_target_flows": True,
		"trs_maxtime": 0.001,

		"split_codings": True,
		"feature_max": 18,

	}

	deps = []

	# model stuff
	(model_prefix, spiffy_mode) = models[model]
	params["spiffy_mode"] = spiffy_mode

	discount = expt_part(discounts, deps)
	params["discount"] = discount
	deps.append(discounts)

	# host count stuff.
	(host_p, dt) = expt_part(host_ps, deps)
	params["host_range"] = [host_p, host_p]
	params["dt"] = dt
	deps.append(host_ps)

	# Traffic model stuff
	(traffic_prefix, is_tcp) = expt_part(traffic_types, deps)
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
	deps.append(traffic_types)

	broken_math = expt_part(maths, deps)
	params["broken_math"] = broken_math
	if not broken_math:
		# Need to reduce alpha
		# convergence guarantees and all that
		# reduce it by ratio of active tiles
		# The high choice works if the tiles are all 
		# learning independently (broken math)
		#params["alpha"] = params["alpha"] * 9.0 / 121.0
		pass
	print params["alpha"]
	deps.append(maths)

	algo = expt_part(algos, deps)
	params["algo"] = algo
	deps.append(algos)

	(indiv_prefix, single_learner) = expt_part(single_learners, deps)
	params["single_learner"] = single_learner
	params["estimate_const_limit"] = True
	deps.append(single_learners)

	(measure_prefix, measure) = expt_part(measures, deps)
	params["record_deltas_in_times"] = measure
	deps.append(measures)

	results = marlExperiment(**params)
	(rewards, good_traffic_percents, total_loads, store_sarsas, rng, action_comps) = results

	file_name_part = "bmath-{}{}".format(broken_math, measure_prefix)
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
	#print "{} would write to: {}".format(experiment, csv_dir)
