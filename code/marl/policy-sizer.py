import cPickle as pickle
import numpy as np

rd = "../../results/"
srcs = []

with open(rd + "ftprep-tcp-cap.pickle") as of:
	ftp = pickle.load(of)

with open(rd + "bonus-ftprep-tcp-cap.pickle") as of:
	bftp = pickle.load(of)

sizes = []
for (lep, rep) in zip(ftp, bftp):
	(_rng, sarsas) = lep
	sarsas += rep[1]
	local_sizes = []

	for (s_tree, restrict) in sarsas:
		a_cnt = 0
		#if isinstance(s_tree)
		for team in s_tree:
			for agent in team:
				if len(local_sizes) <= a_cnt:
					local_sizes.append(0.0)
				local_sizes[a_cnt] += float(len(agent.values) * 10)
				a_cnt += 1
	sizes += local_sizes

print "stats (n_floats): n:{} bytes:{} avg:{} mean:{}".format(len(sizes), np.sum(sizes), np.mean(sizes), np.median(sizes))
print "stats (bytes): avg:{} mean:{}".format(np.mean(sizes) * 4.0, np.median(sizes) * 4.0)
print "stats (kiB): avg:{} mean:{}".format(np.mean(sizes) * 4.0 / 1024.0, np.median(sizes) * 4.0 / 1024.0)
