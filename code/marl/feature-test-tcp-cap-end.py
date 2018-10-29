import cPickle
from marl import *
from writer import writeResults, makeResultsAverage

ft = __import__("feature-test-tcp-cap-prep")

def run(restrict, state, rewards, good_traffic_percents, total_loads, contributors=None, store_sarsas=[], ep_len=10000):
	results = marlExperiment(
		n_teams = 2,

		n_inters = 2,
		n_learners = 3,
		host_range = [ft.hosts_p, ft.hosts_p],

		explore_episodes = 0.8,
		episodes = 1,
		episode_length = ep_len,
		separate_episodes = True,

		alpha = 0.05,
		epsilon = 0.2,
		discount = 0,

		dt = 0.05,

		rf = "ctl",
		use_controller = True,
		actions_target_flows = restrict is not None,

		restrict = restrict,

		rand_state = state,
		rewards = rewards,
		good_traffic_percents = good_traffic_percents,
		total_loads = total_loads,

		contributors = contributors,
		store_sarsas = store_sarsas,

		evil_range = [4,7],
		model = "nginx",
		reward_direction = "out",
		randomise = True,
		randomise_count = 3,
		randomise_new_ip = True,

		manual_early_limit = 26.0,
	)

	return results

# For each episode, we want to...
# - Try each feature with G as a contributor (who has restriction [0,1,2,3]).
# - Start with G as a contributor, but then learn each feature from scratch.

combo_result_sets = [([], [], []) for i in xrange(ft.n_features)]
fresh_result_sets = [([], [], []) for i in xrange(ft.n_features)]

configs = [
	(combo_result_sets, False, "combine", 3000),
	#(fresh_result_sets, True, "fresh", 10000)
]

if __name__ == "__main__":
	with open(ft.file_dir, "rb") as of:
		data = cPickle.load(of)

	for (randstate, contributors) in data:
		g_contrib = (contributors[0][0], [a for a in xrange(4)])

		feature_contribs = contributors[1:]

		for (target_results, start_fresh, _, ep_len) in configs:
			for j, (sarsa_tree, restriction) in enumerate(feature_contribs):
				(rewards, good_traffic_percents, total_loads) = target_results[j]
				(rs, gs, ls, store_sarsas, rng_state, _) = run(
					restriction,
					randstate[1],
					rewards, good_traffic_percents, total_loads,
					contributors=[g_contrib],
					store_sarsas=[] if start_fresh else sarsa_tree,
					ep_len=ep_len
				)

				target_results[j] = (rs, gs, ls)

	# Now, write out the results!
	for (target_results, start_fresh, config_name, ep_len) in configs:
		for i, (rs, gs, ls) in enumerate(target_results):
			csv_dir = ft.results_dir + "ft-tcp-cap-{}-f{}.csv".format(config_name, i)
			avg_csv_dir = ft.results_dir + "ft-tcp-cap-{}-f{}-avg.csv".format(config_name, i)

			results = (rs, gs, ls, None, None, None)

			writeResults(csv_dir, results)
			makeResultsAverage(csv_dir, avg_csv_dir)
