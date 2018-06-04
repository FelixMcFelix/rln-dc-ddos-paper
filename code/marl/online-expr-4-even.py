from marl import *
from writer import writeResults, makeResultsAverage

hosts_p = 4

results = marlExperiment(
	n_teams = 2,#5,

	n_inters = 2,
	n_learners = 3,
	host_range = [hosts_p, hosts_p],

	explore_episodes = 0.3,
	episodes = 10,#500, Since mininet keeps running out of files even e/ cleanup
	episode_length = 10000,
	separate_episodes = True,

	alpha = 0.05,
	epsilon = 0.2,
	discount = 0,
	break_equal = True,

	dt = 0.05,#0.01,

	rf = "ctl",

	rand_seed = 0xcafed00d
)

writeResults("../../results/online-4-even.csv", results)

makeResultsAverage("../../results/online-4-even.csv", "../../results/online-4-even-avg.csv")

