import cPickle
from marl import *
import sys
from writer import writeResults, makeResultsAverage

ft = __import__("tcp-model-combo-prep")

def run(restrict, state, rewards, good_traffic_percents, total_loads, contributors=None, store_sarsas=[], ep_len=10000, h_p=2):
	results = marlExperiment(
		n_teams = 2,

		n_inters = 2,
		n_learners = 3,
		host_range = [h_p, h_p],

		explore_episodes = 0.8,
		episodes = 1,
		episode_length = ep_len,
		separate_episodes = True,

		alpha = 0.05,
		epsilon = 0.2,
		discount = 0,

		dt = 0.01,

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

		estimate_const_limit = True,
	)

	return results

# For each episode, we want to...

host_ps = [2, 4, 8, 16]
host_ps = [ host_ps[int(sys.argv[1])] ]
combo_result_sets = [([], [], []) for a in host_ps]

configs = [
	#(combo_result_sets, False, "combine", 3000),
	# Temp Test to see longterm...
	(combo_result_sets, False, "combine", 10000),
]

if __name__ == "__main__":
	with open(ft.file_dir, "rb") as of:
		data = cPickle.load(of)

	for (randstate, contributors) in data:
		g_contrib = (contributors[0][0], [a for a in xrange(4)])

		feature_contribs = contributors[1:]

		for (target_results, start_fresh, _, ep_len) in configs:
			for j, h_p in enumerate(host_ps):
				(rewards, good_traffic_percents, total_loads) = target_results[j]
				(rs, gs, ls, store_sarsas, rng_state, _) = run(
					g_contrib[1],
					randstate[1],
					rewards, good_traffic_percents, total_loads,
					# contributors=[g_contrib],
					contributors=feature_contribs,
					store_sarsas=[] if start_fresh else g_contrib[0],
					ep_len=ep_len,
					h_p=h_p,
				)

				target_results[j] = (rs, gs, ls)

	# Now, write out the results!
	for (target_results, start_fresh, config_name, ep_len) in configs:
		for h_p, (rs, gs, ls) in zip(host_ps, target_results):
			csv_dir = ft.results_dir + "tcp-combo-{}.csv".format(h_p)
			avg_csv_dir = ft.results_dir + "tcp-combo-{}-avg.csv".format(h_p)

			results = (rs, gs, ls, None, None, None)

			writeResults(csv_dir, results)
			makeResultsAverage(csv_dir, avg_csv_dir)
