from mininet.topo import Topo
from mininet.node import OVSSwitch, RemoteController
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.net import Mininet
from mininet.clean import Cleanup

import itertools
import numpy as np
from sarsa import SarsaLearner
from subprocess import PIPE, Popen
import sys
import time

# config
linkopts = {
#	"bw": 10
}

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

dt = 0.001

# reward functions: choose wisely!

def std_marl(total_svr_load, legit_svr_load, true_legit_svr_load,
		total_leader_load, legit_leader_load, true_legit_leader_load,
		num_teams, max_load):
	svr_fail = total_svr_load > max_load
	return -1 if svr_fail else legit_svr_load/true_legit_svr_load

def itl(total_svr_load, legit_svr_load, true_legit_svr_load,
		total_leader_load, legit_leader_load, true_legit_leader_load,
		num_teams, max_load):
	leader_fail = total_leader_load > (float(max_load)/num_teams)
	return -1 if leader_fail else legit_leader_load/true_legit_leader_load

def ctl(total_svr_load, legit_svr_load, true_legit_svr_load,
		total_leader_load, legit_leader_load, true_legit_leader_load,
		num_teams, max_load):
	svr_fail = total_svr_load > max_load
	leader_fail = total_leader_load > (float(max_load)/num_teams)
	return -1 if (svr_fail and leader_fail) else legit_leader_load/true_legit_leader_load

reward_func = ctl

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

initd_host_count = 0
initd_switch_count = 0
def newNamedHost(**kw_args):
	global initd_host_count
	o = net.addHost("h{}".format(initd_host_count), **kw_args)
	initd_host_count += 1
	return o
def newNamedSwitch(**kw_args):
	global initd_switch_count
	o = net.addSwitch("s{}".format(initd_switch_count), **kw_args)
	initd_switch_count += 1
	return o

def trackedLink(src, target, extras=None):
	if extras is None:
		extras = linkopts
	# print src.name, target.name
	l = net.addLink(src, target, **extras)
	# links.append(l)
	return l

def updateUpstreamRoute(switch, out_port=0, ac_prob=0.0):
	# Turn from prob_drop into prob_send!
	prob = ac_prob - 1
	name = switch.name
	p_drop = "" if ac_prob == 0.0 else "probdrop:{},".format(pdrop(prob))

	# really lazy -- big one-directional route. But that's all we need for now.
	switch.cmd(
		"sh",
		"ovs-ofctl",
		"addflow",
		name,
		"in_port=*,actions={}\"{}-eth{}\"".format(p_drop, name, out_port)
	)

def routedSwitch(upstreamNode, **args):
	sw = newNamedSwitch(**args)
	trackedLink(upstreamNode, sw)
	updateUpstreamRoute(sw)
	return sw

def enactActions(learners):
	for (node, sarsa) in learners:
		(_, action, _) = sarsa.last_act
		updateUpstreamRoute(node, ac_prob=action)

def addHosts(extern, hosts_per_learner, hosts_upper):
	host_count = (hosts_per_learner if hosts_per_learner == hosts_upper
		else np.random.randint(hosts_per_learner, hosts_upper)
	)

	hosts = []

	for i in xrange(host_count):
		new_host = newNamedHost()
		good = np.random.uniform() < P_good
		bw = (np.random.uniform(*(good_range if good else evil_range)))

		trackedLink(extern, new_host, {"bw": bw})

		hosts.append(
			(new_host, good, bw)
		)
	return hosts

def makeTeam(parent, inter_count, learners_per_inter):
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

	for (host, _, _) in hosts:
		# print "killing", host.name
		host.stop()

	new_hosts = []

	for extern in extern_switches:
		new_hosts += addHosts(extern, hosts_per_learner, hosts_upper)

	return (leader, intermediates, learners, extern_switches, new_hosts)

def buildNet(n_teams):
	server = newNamedHost()
	server_switch = newNamedSwitch()
	core_link = trackedLink(server, server_switch)

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

tracked_switches = [server_switch] + list(itertools.chain.from_iterable([
	[leader] + intermediates + [l[0] for l in learners] for (leader, intermediates, learners, _, _) in teams
]))

tracked_interfaces = ["{}-eth1".format(el.name) for el in tracked_switches]

switch_list_indices = {}
for i, sw in enumerate(tracked_switches):
	switch_list_indices[sw.name] = i

for ep in xrange(episodes):
	print "beginning episode {} of {}".format(ep+1, episodes)
	# remake/reclassify hosts
	all_hosts = []
	l_teams = []

	bw_teams = []
	# good, bad, total
	bw_all = [0.0 for i in xrange(3)]

	# Assign hosts again, and memorise the load they intend to push.
	for team in teams:
		new_team = makeHosts(team, *host_range)
		new_hosts = new_team[4]

		# need to know the intended loads of each class (overall and per-team).
		# good, bad, total
		bw_stats = [0.0 for i in xrange(3)]
		for (host, good, bw) in new_hosts:
			if good:
				bw_stats[0] += bw
				bw_all[0] += bw
			else:
				bw_stats[1] += bw
				bw_all[1] += bw
			bw_stats[2] += bw
			bw_all[2] += bw

		bw_teams.append(bw_stats)
		all_hosts += new_hosts

		l_teams.append(new_team)
	teams = l_teams

	# Per team stuff - 
	for (_, _, learners, _, _) in teams:
		for (node, sarsa) in learners:
			# reset network model to default rules.
			updateUpstreamRoute(node)

			# Assume initial state is all zeroes (new network)
			sarsa.bootstrap(sarsa.to_state(np.zeros(sarsaParams["vec_size"])))
	
	# Update master link's bandwidth limit after hosts init.
	# core_link.config(bw=calc_max_capacity(len(all_hosts)))

	# Begin the new episode!
	net.start()

#	net.interact()

	# Spool up the monitoring tool.
	mon_cmd = server_switch.popen(
		["../marl-bwmon/marl-bwmon"] + tracked_interfaces,
		stdin=PIPE,
		stderr=sys.stderr
	)

	# TODO: gen traffic at each host.

	for i in xrange(episode_length):
		if not (i % 10): print "\titer {}/{}".format(i, episode_length)
		# Make the last actions a reality!
		for (_, _, learners, _, _) in teams:
			enactActions(learners)

		# Wait, somehow
		time.sleep(dt)

		# Measure good/bad loads!
		mon_cmd.stdin.write("\n")
		mon_cmd.stdin.flush()
		data = mon_cmd.stdout.readline().strip().split(",")

		time_ns = int(data[0][:-2])
		load_mbps = [map(
				lambda bytes: (8000*float(bytes))/time_ns,
				el.strip().split(" ")
			) for el in data[1:]
		]

		total_mbps = [good+bad for (good, bad) in load_mbps]

		for team_no, (leader, intermediates, learners, _, _) in enumerate(teams):
			team_true_loads = bw_teams[team_no]

			leader_index = switch_list_indices[leader.name]

			# Compute reward!
			reward = reward_func(total_mbps[0], load_mbps[0][0], bw_all[0],
				total_mbps[leader_index], load_mbps[leader_index][0], bw_teams[team_no][0],
				n_teams, len(all_hosts))

			for learner_no, (node, sarsa) in enumerate(learners):
				# Encode state (as seen by this learner)
				important_indices = [switch_list_indices[name] for name in [
					intermediates[learner_no/n_learners].name, node.name
				]]

				state_vec = np.array([total_mbps[index] for index in [0, leader_index]+important_indices])
				state = sarsa.to_state(state_vec)

				# Learn!
				sarsa.update(state, reward)

	# End this monitoring instance.
	mon_cmd.stdin.close()

	net.stop()

# Run interesting stats stuff here? Just save the results? SAVE THE LEARNED MODEL?!
