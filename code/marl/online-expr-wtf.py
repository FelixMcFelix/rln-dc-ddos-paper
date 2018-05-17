from marl import *
from writer import writeResults, makeResultsAverage

total = 500.0
n_hosts = 100

bestrange = [total / n_hosts for x in xrange(2)]
hostrange = [n_hosts for x in xrange(2)]

results = marlExperiment(
	P_good = 1,
	n_teams = 1,

	n_inters = 1,
	n_learners = 1,
	host_range = hostrange,

	good_range = bestrange,
	evil_range = bestrange,

	explore_episodes = 0.3,
	episodes = 50,#500, Since mininet keeps running out of files even e/ cleanup
	episode_length = 10000,
	separate_episodes = True,

	alpha = 0.05,
	epsilon = 0.2,
	discount = 0,

	dt = 0.01,

	old_style = False,
	break_equal = True,

	rf = "ctl"
)

#writeResults("../../results/online-wtf.csv", results)

#makeResultsAverage("../../results/online-wtf.csv", "../../results/online-wtf-avg.csv")
