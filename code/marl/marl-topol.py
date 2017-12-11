from mininet.topo import Topo
from mininet.node import OVSSwitch, RemoteController
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.net import Mininet
from mininet.clean import Cleanup

import numpy as np
import pypcap
from sarsa import SarsaLearner
import time

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

dt = 0.05

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

def updateUpstreamRoute(switch, out_port=0, ac_prob=0.0):
	# Turn from prob_drop into prob_send!
	prob = ac_prob - 1
	name = switch.name
	p_drop = "" if ac_prob == 0.0 else "probdrop:{},".format(pdrop(prob))

	# really lazy -- big one-directional route. But that's all we need for now.
	net.cmd(
		"sh",
		"ovs-ofctl",
		"addflow",
		name,
		"in_port=*,actions={}\"{}-eth{}\"".format(p_drop, name, out_port)
	)

def routedSwitch(upstreamNode, **args):
	sw = net.addSwitch(**args)
	trackedLink(upstreamNode, sw)
	updateUpstreamRoute(sw)
	return sw

def enactAction(learners):
	for (node, sarsa) in learners:
		(_, action, _) = sarsa.last_act
		updateUpstreamRoute(node, ac_prob=action)

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

	leader = routedSwitch(parent)

	intermediates = []
	learners = []
	extern_switches = []
	hosts = []

	for i in xrange(inter_count):
		new_interm = routedSwitch(leader)
		intermediates.append(new_interm)

		for j in xrange(learners_per_inter):
			new_learn = routedSwitch(new_interm)

			# Init and pair the actual learning agent here, too!
			# Bootstrapping happens later -- per-episode, in the 0-load state.
			sar = SarsaLearner(**sarsaParams)
			
			learners.append(
				(new_learn, SarsaLearner(**sarsaParams))
			)

			new_extern = routedSwitch(new_learn)
			extern_switches.append(new_extern)

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
		bw.append(
			np.random.uniform(*(good_range if good_host else bad_range))
		)

	# reset network model to default rules.
	for (_, _, learners, _, _) in teams:
		for (node, sarsa) in learners:
			updateUpstreamRoute(node)

			# Assume initial state is all zeroes (new network)
			sarsa.bootstrap(sar.tc(np.zeros(sarsaParams[vec_size])))

	# TODO: pypcap monitor elected switches for reward functions.
	# TODO: gen traffic at each host
	# TODO: update master link's bandwidth limit after host init.

	net.start()

	for i in xrange(episode_length):
		# Make the last actions a reality!
		for (_, _, learners, _, _) in teams:
			enactAction(learners)

		# Wait, somehow
		time.sleep(dt)

		for (leader, intermediates, learners, _, _) in teams:
			# Measure state!
			# TODO

			# Compute reward!
			# TODO

			# Learn!
			# TODO

	net.stop()

# Run intersting stats stuff here? Just save the results? SAVE THE LEARNED MODEL?!