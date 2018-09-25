from marl import *
from writer import writeResults, makeResultsAverage

hosts_p = 4

results = marlExperiment(
	n_teams = 2,#5,

	n_inters = 2,
	n_learners = 3,
	host_range = [hosts_p, hosts_p],

	explore_episodes = 0.8,
	episodes = 10,#50,#500, Since mininet keeps running out of files even e/ cleanup
	episode_length = 100000,
	separate_episodes = True,

	alpha = 0.05,
	epsilon = 0.2,
	discount = 0,

	dt = 0.05,

#	old_style=True,

	rf = "ctl",
	use_controller = True,
	actions_target_flows = True,

	#estimate_const_limit = True,
)

writeResults("../../results/soln-ext-4.csv", results)

makeResultsAverage("../../results/soln-ext-4.csv", "../../results/soln-ext-4-avg.csv")
