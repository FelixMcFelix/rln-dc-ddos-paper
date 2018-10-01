from marl import *
from writer import writeResults, makeResultsAverage

host_p = 4 

results = marlExperiment(
	n_teams = 2,#5,

	n_inters = 2,
	n_learners = 3,
	host_range = [host_p, host_p],

	explore_episodes = 0.8,
	episodes = 10,#50,#500, Since mininet keeps running out of files even e/ cleanup
	episode_length = 10000,
	separate_episodes = True,

	alpha = 0.05,
	epsilon = 0.2,
	discount = 0,

	dt = 0.05,#0.01,

#	old_style=True,

	rf = "ctl"
)

writeResults("../../results/online-4-e-8.csv", results)

makeResultsAverage("../../results/online-4-e-8.csv", "../../results/online-4-e-8-avg.csv")
