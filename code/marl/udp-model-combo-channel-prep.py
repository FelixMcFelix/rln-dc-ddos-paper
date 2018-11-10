import cPickle
from marl import *
import sys
from writer import writeResults, makeResultsAverage

def run(restrict, state, rewards, good_traffic_percents, total_loads, h_p):
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


		dt = 0.01,

	#	old_style=True,

		rf = "ctl",
		use_controller = True,
		actions_target_flows = restrict is not None,

		restrict = restrict,

		rand_state = state,
		rewards = rewards,
		good_traffic_percents = good_traffic_percents,
		total_loads = total_loads,

		#evil_range = [4,7],
		model = "nginx",
		submodel = "udp-flood",
		#reward_direction = "out",
		#randomise = True,
		#randomise_count = 3,
		#randomise_new_ip = True,

		estimate_const_limit = True,
	)

	return results

# Run one set to old mode, run 8 on restrict [4+i for i in xrange(8)]
# Build up results each time, should have 9 sets. collect RNG states for each set

host_ps = [2, 4, 8, 16]
results_dir = "../../results/"
file_dir = results_dir + "udp-combo-channel-prep-{}.pickle"
in_progress_file_dir = results_dir + "udp-combo-channel-prg-{}.pickle"
chosen_features = [
	5, # Mean IAT
	7, # Delta Out Rate
	6, # Delta In Rate
]
n_episodes = 10
n_episodes_per_step = 5
restrict_sets = [None] + [[4 + i] for i in chosen_features]
out_names = ["g"] + ["f{}".format(i) for i in chosen_features]

result_sets = [([], [], []) for i in xrange(1 + len(chosen_features))]

if __name__ == "__main__":
	# read from first arg
	hosts_p = host_ps[int(sys.argv[1])]
	file_dir = file_dir.format(hosts_p)
	in_progress_file_dir = in_progress_file_dir.format(hosts_p)

	# if second arg exists, then we're "in-progress"
	# pickle has last experiment state...
	start_i = 0
	in_progress = len(sys.argv) > 2

	if in_progress:
		with open(in_progress_file_dir, "rb") as of:
			(start_i, result_sets, things_to_pickle) = cPickle.load(of)

	things_to_pickle = []

	randstate = None
	for i in xrange(start_i, start_i + n_episodes_per_step):
		state = (i, randstate)
		agents = []
		for j, restriction in enumerate(restrict_sets):
			(rewards, good_traffic_percents, total_loads) = result_sets[j]
			(rs, gs, ls, store_sarsas, rng_state, _) = run(
				restriction,
				state[1],
				rewards, good_traffic_percents, total_loads,
				hosts_p
			)

			result_sets[j] = (rs, gs, ls)
			randstate = rng_state

			# list of: each set of agents, and the filtered
			agents.append((store_sarsas, restriction))

		# list of: rng states and the set of agents generated from each.
		things_to_pickle.append((state, agents))
	start_i += n_episodes_per_step

	# what to do if still work to do? give up.
	if start_i < n_episodes:
		with open(in_progress_file_dir, "wb") as of:
			cPickle.dump((start_i, result_sets, things_to_pickle), of)
		sys.exit(0)

	# Now, save out the sarsas.
	with open(file_dir, "wb") as outfile:
		cPickle.dump(things_to_pickle, outfile)

	# Now, write out the results!
	for ((rs, gs, ls), out_name) in zip(result_sets, out_names):
		csv_dir = results_dir + "udp-combo-channel-prep-{}-{}.csv".format(out_name, hosts_p)
		avg_csv_dir = results_dir + "udp-combo-channel-prep-{}-{}-avg.csv".format(out_name, hosts_p)

		results = (rs, gs, ls, None, None, None)

		writeResults(csv_dir, results)
		makeResultsAverage(csv_dir, avg_csv_dir)
