from marl import *
from writer import writeResults, makeResultsAverage
import cPickle
import sys

state = ([], None)

filedir = sys.argv[1]
block_size = int(sys.argv[2])
total_size = int(sys.argv[3])
should_read = bool(int(sys.argv[4]))

if should_read:
	with open(filedir, "rb") as infile:
		state = cPickle.load(infile)

(store_sarsas, random_state) = state

results = marlExperiment(
	n_teams = 5,

	n_inters = 2,
	n_learners = 3,
	host_range = [2, 2],

	explore_episodes = 0.8*total_size,
	episodes = block_size,
	episode_length = 1000,
	separate_episodes = False,

	alpha = 0.05,
	epsilon = 0.3,
	discount = 0,
	break_equal = True,

	dt = 0.01,

#	old_style=True,

	with_ratio = True,

	rf = "ctl",

	store_sarsas = store_sarsas,
	rand_state = random_state,
)

(_, _, _, store_sarsas, random_state, _) = results

writeResults("../../results/offline.csv", results, append=True)

with open(filedir, "wb") as outfile:
	cPickle.dump((store_sarsas, random_state), outfile)

