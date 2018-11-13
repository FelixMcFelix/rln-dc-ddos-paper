from collections import Counter
import cPickle as pickle
import csv
import numpy as np

results_dir = "../../results/"
pickle_chooser = "tcp-combo-channel-prep-{}.pickle"
out_file = "tcp-action-f{}-{}-{}.csv"

restricts = [5, 6, 7]
txrestricts = [a + 4 for a in restricts]
windows = [
	(0, 10000),
	(-50, 50),
	(-50, 50),
]
n_steps = 48

ns = [2, 4, 8, 16]

factor = 1/10.0

for n in ns:
	len_holder = {}
	for i in txrestricts:
		len_holder[(i,)] = []
	len_holder[(0,)] = []

	choice_holders = [{} for i in windows]
		
	f_dir = results_dir + pickle_chooser.format(n)
	with open(f_dir, "rb") as of:
		q = pickle.load(of)

	for (_rng, ep) in q:
		for (a_tree, restrict) in ep:
			for team in a_tree:
				for agent in team:
					#print "n:{} -- {}".format(n, len(agent.values))
					place = (0,) if restrict is None else tuple(restrict)
					len_holder[place].append(len(agent.values))
					if restrict is not None:
						truth = restrict[0] - 4
						ind = restricts.index(truth)
						(lower, upper) = windows[ind]
						start = float(lower)
						move = (float(upper) - start)/float(n_steps)
						space = choice_holders[ind]

						curr = start - move
						end = upper + move

						#print curr, end, move
						while curr < end:
							if curr not in space:
								space[curr] = ([], [])
							s = agent.tc(np.array([curr]))
							vals = agent.select_action(s)
							space[curr][0].append(vals[0])
							space[curr][1].append(vals[2])
							#print curr, vals[2]
							curr += move
						
	for (k, v) in len_holder.iteritems():
		print "For n={} and feature {}, avg occ={}".format(n, k, np.mean(v))

	for i, space in enumerate(choice_holders):
		x_vals = []
		mosts = []
		means = []
		avs = []
		avm = []
		for (p_set, (action_choices, a_vals)) in space.iteritems():
			c = Counter(action_choices)
			x_vals.append(p_set)
			q = c.most_common(4)
			#print q
			mosts.append(q[0][0])
			means.append(np.median(action_choices))
			avs.append(np.sum(a_vals, axis=0))
			avm.append(np.mean(a_vals, axis=0))

		order = np.argsort(x_vals)
		nx = np.array(x_vals)[order]
		nmo = np.array(mosts)[order]
		nme = np.array(means)[order]
		avso = np.array(avs)[order]
		avmo = np.array(avm)[order]

		#print "n={}, feat={}, most_ac={}".format(n, i, nmo)
		#print "mean_ac={}".format(nme)
		#print "sum_policy={}".format(avso)
		#print "mean_policy={}".format(avmo)

		things = [
			("mode-a", nmo, False),
			("mean-a", nme, False),
			("sum-p", avso, True),
			("mean-p", avmo, True),
		]

		f_no = restricts[i]
		for (name, data, is_matrix) in things:
			print data.shape
			with open(results_dir + out_file.format(f_no, n, name), "wb") as of:
				writ = csv.writer(of)
				rest_header = [str(i) for i in xrange(data.shape[1])] if is_matrix else ["action"]
				writ.writerow(["#x"] + rest_header)
				for j, row in enumerate(data):
					if not is_matrix:
						row = [row]
					writ.writerow([nx[j]] + list(row))
