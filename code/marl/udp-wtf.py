from marl import *
from writer import writeResults, makeResultsAverage

results = marlExperiment(
	P_good = 1,
	n_teams = 2,#5,

	n_inters = 1,
	n_learners = 1,
	host_range = [1, 1],

	explore_episodes = 0.3,
	episodes = 10,#50,#500, Since mininet keeps running out of files even e/ cleanup
	episode_length = 10000,
	separate_episodes = True,

	alpha = 0.05,
	epsilon = 0.2,
	discount = 0,

	model = "nginx",
	submodel = "udp-flood",

	dt = 0.05,#0.01,

#	old_style=True,

	rf = "ctl",
	use_controller = True,
)

#writeResults("../../results/ag-udp.csv", results)

#makeResultsAverage("../../results/ag-udp.csv", "../../results/ag-udp-avg.csv")
