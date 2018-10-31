import logging
from marl import *
from writer import writeResults, makeResultsAverage

host_p = 2 

results = marlExperiment(
	n_teams = 2,#5,

	n_inters = 2,
	n_learners = 3,
	host_range = [host_p, host_p],

	# test to handle bi-directional
	evil_range = [4, 7],

	explore_episodes = 0.8,
	episodes = 10,#50,#500, Since mininet keeps running out of files even e/ cleanup
	episode_length = 10000,
	separate_episodes = True,

	alpha = 0.05,
	epsilon = 0.2,
	discount = 0.6,

	#model = "nginx",

	dt = 0.05,#0.01,

#	old_style=True,

	rf = "ctl",
	use_controller = True,

	#reward_direction = "out",
	actions_target_flows = True,
	#estimate_const_limit = True,

	spiffy_mode = True,
	#randomise = True,
	#randomise_count = 1,
	#randomise_new_ip = True,

	split_codings = True,
	trs_maxtime = 0.001,
	feature_max = 18,
	single_learner = True,
)

writeResults("../../results/spf-d3.csv", results)

makeResultsAverage("../../results/spf-d3.csv", "../../results/spf-d3-avg.csv")
