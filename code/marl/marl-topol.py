from mininet.topo import Topo
from mininet.node import OVSSwitch, RemoteController
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.net import Mininet
from mininet.clean import Cleanup

import numpy as np
import pypcap
from sarsa import SarsaLearner

# config
linkopts = {"bw": 10}

n_teams = 1
# per-team options
n_inters = 2
n_learners = 3
host_range = [2, 2]

calc_max_capacity = lambda hosts: good_range[1]*hosts + 2

P_good = 0.6
good_range = [0, 1]
evil_range = [2.5, 6]

episodes = 80000
episode_length = 1000

max_bw = n_teams * n_inters * n_learners * host_range[1] * evil_range[1]
pdrop_magnitudes = [0.1*n for n in xrange(10)]

alpha = 0.05
epsilon = 0.3
discount = 0

# gen

sarsaParams = {
	"max_bw": max_bw,
	"vec_size": 4,
	"actions": pdrop_magnitudes,
	"epsilon": epsilon,
	"learn_rate": alpha,
	"discount": discount,
	# "tile_c": 16,
	# "tilings_c": 3,
	# "default_q": 0,
	# "epsilon_falloff": 1000
}

# helpers

def trackedLink(src, target, extras=None):
	if extras is None:
		extras = linkopts

	l = net.addLink(src, target, **extras)
	# links.append(l)
	return l

def maybeLink(target):
	if target <= len(switches):
		si = int(target/2)-1
		ti = target-1
		trackedLink(switches[si], switches[ti])

def addHosts(extern, hosts_per_learner, hosts_upper=None):
	host_count = np.random.randint(hosts_per_learner, hosts_upper)

	hosts = []

	for i in xrange(host_count):
		new_host = net.addHost()
		trackedLink(extern, new_host)
		hosts.append(new_host)

	return hosts

def makeTeam(parent, inter_count, learners_per_inter):
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

			# Init and pair the actual learning agent here, too!
			# Assume initial state is all zeroes
			# Use the "last_act" so we know what to expect.
			sar = SarsaLearner(**sarsaParams)
			sar.bootstrap(sar.tc(np.zeros(sarsaParams[vec_size])))
			
			learners.append(
				(new_learn, SarsaLearner(**sarsaParams))
			)

			new_extern = net.addSwitch()
			trackedLink(new_extern, new_learn)
			extern_switches.append(new_extern)

	# TODO: put in rules w/ dpctl for routing

	return (leader, intermediates, learners, extern_switches, hosts)

def makeHosts(team, hosts_per_learner, hosts_upper=None):
	if hosts_upper is None:
		hosts_upper = hosts_per_learner

	(leader, intermediates, learners, extern_switches, hosts) = team

	for host in hosts:
		net.delHost(host)

	new_hosts = []

	for extern in extern_switches:
		new_hosts += addHosts(extern, hosts_per_learner, hosts_upper)

	# TODO: dpctl routing from extern inwards.

	return (leader, intermediates, learners, extern_switches, new_hosts)

def buildNet(n_teams):
	server = host.addHost()
	server_switch = host.addSwitch()
	core_link = trackedLink(server, server_switch, {"bw": 10}) # TODO: set accurately.

	teams = []
	for i in xrange(n_teams):
		t = makeTeam(server_switch, n_inters, n_learners)
		trackedLink(server_switch, t[0])
		teams.append(t)

	return (server, server_switch, core_link, teams)

def pdrop(prob):
	return int(prob * 0xffffffff)

def enactAction(learners):
	pass # TODO

### THE EXPERIMENT? ###

# initialisation

Cleanup.cleanup()

net = Mininet(link=TCLink)

# May be useful to keep around
#net.addController("c0", controller=RemoteController, ip="127.0.0.1", port=6633)

# build network model once, remove/reattach/reclassify hosts per-episode
(server, server_switch, core_link, teams) = buildNet(n_teams)

for ep in xrange(episodes):
	# remake/reclassify hosts
	all_hosts = []
	l_teams = []
	for team in teams:
		n_team = makeHosts(team, *host_range)
		all_hosts += n_team[4]
		l_teams.append(n_team)
	teams = l_teams

	# per-host stuff
	good = []
	bw = []
	for host in allhosts:
		good_host = np.random.uniform() < P_good
		good.append(good_host)
		bw.append(np.random.uniform(
			*(good_range if good_host else bad_range)
		)

	# reset network model to default rules.
	# TODO -- dpctl?

	# TODO: map each switch to its upstream link. (s*-eth0 should always be "upstream")
	# TODO: pypcap monitor elected switches for reward functions.
	# TODO: gen traffic at each host

	net.start()

	for i in xrange(episode_length):
		# Wait, somehow
		# TODO

		for (leader, intermediates, learners, _, _) in teams:
			# Measure state!
			# TODO

			# Compute reward!
			# TODO

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
