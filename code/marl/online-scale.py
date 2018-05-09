from marl import *
from writer import writeResults, makeResultsAverage

results = marlExperiment(
	n_teams = 5,

	n_inters = 2,
	n_learners = 3,
	host_range = [2, 2],

	explore_episodes = 0.3,
	episodes = 10,#50,#500, Since mininet keeps running out of files even e/ cleanup
	episode_length = 10000,
	separate_episodes = True,

	alpha = 0.05,
	epsilon = 0.2,
	discount = 0,

	dt = 0.05,#0.01,

#	old_style=True,

	with_ratio = True,

	rf = "ctl"
)

writeResults("../../results/online-scale.csv", results)

makeResultsAverage("../../results/online-scale.csv", "../../results/online-scale-avg.csv")

