from mininet.topo import Topo
from mininet.node import OVSSwitch, RemoteController
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.net import Mininet
from mininet.clean import Cleanup

import numpy as np
import pypcap
from sarsa import SarsaLearner

#config
linkopts = {"bw": 10}

n_teams = 2
P_good = 0.6
goodrange = [0, 1]
evilrange = [2.5, 6]
hostrange = [2, 2]

episodes = 80000
episode_length = 1000

alpha = 0.05
epsilon = 0.3

Cleanup.cleanup()

net = Mininet(link=TCLink)

# May be useful to keep around
#net.addController("c0", controller=RemoteController, ip="127.0.0.1", port=6633)

def trackedLink(src, target):
	l = net.addLink(src, target, **linkopts)
	links.append(l)
	return l

def pdrop(prob):
	return int(prob * 0xffffffff)

def maybeLink(target):
	if target <= len(switches):
		si = int(target/2)-1
		ti = target-1
		trackedLink(switches[si], switches[ti])

def makeTeam(parent, inter_count, learners_per_inter, hosts_per_learner, hosts_upper=None):
	if hosts_upper is None:
		hosts_upper = hosts_per_learner

	leader = net.addSwitch()
	trackedLink(parent, leader)

	intermediates = []
	learners = []
	extern_switches = []
	hosts = []

	for i in xrange(inter_count):
		new_interm = net.addSwitch()
		trackedLink(leader, new_interm)
		intermediates.append(new_interm)

		for j in xrange(learners_per_inter):
			new_learn = net.addSwitch()
			trackedLink(new_interm, new_learn)
			learners.append(new_learn)

			new_extern = net.addSwitch()
			trackedLink(new_extern, new_learn)
			extern_switches.append(new_extern)

			host_count = np.random.randint(hosts_per_learner, hosts_upper)

			for k in xrange(host_count):
				new_host = net.addHost()
				trackedLink(new_extern, new_host)
				hosts.append(new_host)

	# TODO: put in rules w/ dpctl for routing
	# TODO: map each switch to its upstream link. (s*-eth0 should always be "upstream")
	# TODO: pypcap monitor elected switches for reward functions.
	# TODO: map hosts as good/evil

	return (leader, intermediates, learners, extern_switches, hosts)

# build network model once, remove/reattach/reclassify hosts per-episode
# TODO

# Bootstrap here!

for ep in xrange(episodes):
	# reset network model to default rules.

	# reclassify hosts

	net.start()

	for i in xrange(episode_length):
		# Learn!
		# TODO

	net.stop()

# for i, el in enumerate(switches):
# 	ti = i + 1
# 	maybeLink(2*ti)
# 	maybeLink(2*ti + 1)

# # Fix this later to target head, then leaves.
# for i in xrange(3):
# 	trackedLink(hosts[i], switches[i])

# net.start()

#net.waitConnected()
#CLI(net)

# for i, sw in enumerate(switches):
# 	sw.sendCmd("python", "agent.py", i, linkopts["bw"], ">", "{}.txt".format(i))

# ports = {0: (2,3), 2:(1,2)}

# for i in [0,2]:
# 	for p in [ports[i]] + [reversed(ports[i])]:
# 		net.cmd(
# 			"ovs-ofctl addflow s{0} in_port=\"s{0}-eth{1}\",actions=\"s{0}-eth{2}\""
# 			.format(i, *p)
# 		)

#now corrupt one flow for testing.
# net.cmd("ovs-ofctl addflow s2 in_port=\"s2-eth2\",actions=probdrop:{},\"s2-eth1\"".format(
# 	pdrop(0.75)
# ))

#net.iperf((hosts[1],hosts[2]))
#net.iperf((hosts[0],hosts[1]))
#net.iperf((hosts[0],hosts[2]))

# CLI(net)

# net.stop()
