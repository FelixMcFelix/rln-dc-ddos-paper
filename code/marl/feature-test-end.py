import cPickle
from marl import *
from writer import writeResults, makeResultsAverage

ft = __import__("feature-test-prep")

def run(restrict, state, rewards, good_traffic_percents, total_loads, contributors=None, store_sarsas=[]):
	results = marlExperiment(
		n_teams = 2,

		n_inters = 2,
		n_learners = 3,
		host_range = [ft.hosts_p, ft.hosts_p],

		explore_episodes = 0.8,
		episodes = 1,
		episode_length = 10000,
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
	)

	return results

# For each episode, we want to...
# - Try each feature with G as a contributor (who has restriction [0,1,2,3]).
# - Start with G as a contributor, but then learn each feature from scratch.

combo_result_sets = [([], [], []) for i in xrange(ft.n_features)]
fresh_result_sets = [([], [], []) for i in xrange(ft.n_features)]

configs = [
	(combo_result_sets, False, "combine"),
	(fresh_result_sets, True, "fresh")
]

if __name__ == "__main__":
	with open(ft.file_dir, "rb") as of:
		data = cPickle.load(of)

	for (randstate, contributors) in data:
		g_contrib = contributors[0]
		g_contrib[1] = [a for a in xrange(4)]

		feature_contribs = contributors[1:]

		for (target_results, start_fresh, _) in configs:
			for j, (sarsa_tree, restriction) in enumerate(feature_contribs):
				(rewards, good_traffic_percents, total_loads) = target_results[j]
				(rs, gs, ls, store_sarsas, rng_state, _) = run(
					restriction,
					randstate[1],
					rewards, good_traffic_percents, total_loads,
					contributors=[g_contrib],
					store_sarsas=[] if start_fresh else sarsa_tree,
				)

				target_results[j] = (rs, gs, ls)

	# Now, write out the results!
	for (target_results, start_fresh, config_name) in configs:
		for i, (rs, gs, ls) in enumerate(target_results):
			csv_dir = ft.results_dir + "ft-{}-f{}.csv".format(config_name, i)
			avg_csv_dir = ft.results_dir + "ft-{}-f{}-avg.csv".format(config_name, i)

			results = (rs, gs, ls, None, None, None)

			writeResults(csv_dir, results)
			makeResultsAverage(csv_dir, avg_csv_dir)
