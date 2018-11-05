import logging
from marl import *
from writer import writeResults, makeResultsAverage

logging.basicConfig(filename="yawn.log", level=logging.DEBUG)

hosts_p = 16

results = marlExperiment(
	n_teams = 2,#5,

	n_inters = 2,
	n_learners = 3,
	host_range = [hosts_p, hosts_p],

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
	reward_direction = "out",

	evil_range = [4,7],
	randomise = True,
	randomise_count = 3,
	randomise_new_ip = True,
)

writeResults("../../results/online-{}-ng.csv".format(hosts_p), results)

makeResultsAverage("../../results/online-{}-ng.csv".format(hosts_p), "../../results/online-{}-avg-ng.csv".format(hosts_p))
