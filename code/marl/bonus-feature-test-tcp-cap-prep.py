import cPickle
from marl import *
from writer import writeResults, makeResultsAverage

hosts_p = 2

def run(restrict, state, rewards, good_traffic_percents, total_loads):
	results = marlExperiment(
		n_teams = 2,#5,

		n_inters = 2,
		n_learners = 3,
		host_range = [hosts_p, hosts_p],


		explore_episodes = 0.8,
		episodes = 1,
		episode_length = 10000,
		separate_episodes = True,

		alpha = 0.05,
		epsilon = 0.2,
		discount = 0,


		dt = 0.05,

	#	old_style=True,

		rf = "ctl",
		use_controller = True,
		actions_target_flows = restrict is not None,

		restrict = restrict,

		rand_state = state,
		rewards = rewards,
		good_traffic_percents = good_traffic_percents,
		total_loads = total_loads,

		evil_range = [4,7],
		model = "nginx",
		reward_direction = "out",
		randomise = True,
		randomise_count = 3,
		randomise_new_ip = True,

		feature_max = 18,
		estimate_const_limit = True,
	)

	return results

# Run one set to old mode, run 8 on restrict [4+i for i in xrange(8)]
# Build up results each time, should have 9 sets. collect RNG states for each set

results_dir = "../../results/"
file_dir = results_dir + "bonus-ftprep-tcp-cap.pickle"
n_features = 8
n_new_features = 6
n_episodes = 10

restrict_sets = (
#	[[4 + n_features + i] for i in xrange(n_new_features)] +
	[[4 + n_features + i, 5] for i in xrange(n_new_features)]
)

out_names = (
#	["f{}".format(n_features + i) for i in xrange(n_new_features)] +
	["laf,{}".format(n_features + i) for i in xrange(n_new_features)]
)

result_sets = [([], [], []) for i in xrange(len(restrict_sets))]

if __name__ == "__main__":
	things_to_pickle = []

	randstate = None
	for i in xrange(n_episodes):
		state = (i, randstate)
		agents = []
		for j, restriction in enumerate(restrict_sets):
			(rewards, good_traffic_percents, total_loads) = result_sets[j]
			(rs, gs, ls, store_sarsas, rng_state, _) = run(
				restriction,
				state[1],
				rewards, good_traffic_percents, total_loads
			)

			result_sets[j] = (rs, gs, ls)
			randstate = rng_state

			# list of: each set of agents, and the filtered
			agents.append((store_sarsas, restriction))

		# list of: rng states and the set of agents generated from each.
		things_to_pickle.append((state, agents))

	# Now, save out the sarsas.
	with open(file_dir, "wb") as outfile:
		cPickle.dump(things_to_pickle, outfile)

	# Now, write out the results!
	for ((rs, gs, ls), out_name) in zip(result_sets, out_names):
		csv_dir = results_dir + "ft-tcp-cap-{}.csv".format(out_name)
		avg_csv_dir = results_dir + "ft-tcp-cap-{}-avg.csv".format(out_name)

		results = (rs, gs, ls, None, None, None)

		writeResults(csv_dir, results)
		makeResultsAverage(csv_dir, avg_csv_dir)
