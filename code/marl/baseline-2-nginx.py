import logging
from marl import *
from writer import writeResults, makeResultsAverage

logging.basicConfig(filename="yawn.log", level=logging.DEBUG)

results = marlExperiment(
	n_teams = 2,#5,

	n_inters = 2,
	n_learners = 3,
	host_range = [2, 2],

	# test to handle bi-directional
	evil_range = [7, 15],

	explore_episodes = 0.3,
	episodes = 10,#50,#500, Since mininet keeps running out of files even e/ cleanup
	episode_length = 10000,
	separate_episodes = True,

	alpha = 0.05,
	epsilon = 0.2,
	discount = 0,

	model = "nginx",

	dt = 0.05,#0.01,

#	old_style=True,

	rf = "ctl",
	use_controller = True,

	override_action = 0.0,
	manual_early_limit = 26.0,
)

writeResults("../../results/baseline-2-ng.csv", results)

makeResultsAverage("../../results/baseline-2-ng.csv", "../../results/baseline-2-avg-ng.csv")
