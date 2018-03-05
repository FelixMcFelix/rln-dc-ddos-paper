from mininet.topo import Topo
from mininet.node import OVSSwitch, RemoteController
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.net import Mininet
from mininet.clean import Cleanup

import twink.ofp5 as ofp
import twink.ofp5.build as ofpb
import twink.ofp5.parse as ofpp

import itertools
import numpy as np
import os
import random
from sarsa import SarsaLearner
import signal
import socket
from subprocess import PIPE, Popen
import sys
import time

def marlExperiment(
		linkopts = {
		#	"bw": 10
		},
		n_teams = 1,

		# per-team options
		n_inters = 2,
		n_learners = 3,
		host_range = [2, 2],

		calc_max_capacity = None, 

		P_good = 0.6,
		good_range = [0, 1],
		evil_range = [2.5, 6],
		good_file = "../../data/pcaps/bigFlows.pcap",
		bad_file = None,

		explore_episodes = 80000,
		episodes = 1000,#100000
		episode_length = 5000,#1000
		separate_episodes = False,

		max_bw = None,
		pdrop_magnitudes = [0.1*n for n in xrange(10)],

		alpha = 0.05,
		epsilon = 0.3,
		discount = 0,

		dt = 0.001,

		# These should govern tc on the links at various points in the network.
		#
		# Final hop is just what you'd think, old_style governs
		# whether sender rates are mediated by tcpreplay or by tc on the link
		# over from said host.
		old_style = False,
		force_host_tc = False,
		protect_final_hop = True,

		rf = "ctl",

		rand_seed = None,
		rand_state = None,
	):

	# Use any predetermined random state.
	if rand_state is not None:
		random.setstate(rand_state)
	elif rand_seed is not None:
		random.seed(rand_seed)


	if max_bw is None:
		max_bw = n_teams * n_inters * n_learners * host_range[1] * evil_range[1]

	if bad_file is None:
		bad_file = good_file

	if calc_max_capacity is None:
		calc_max_capacity = lambda hosts: good_range[1]*hosts + 2

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

	rfs = {
		"marl": std_marl,
		"itl": itl,
		"ctl": ctl
	}

	reward_func = rfs[rf]

	def safe_reward_func(f, total_svr_load, legit_svr_load, true_legit_svr_load,
			total_leader_load, legit_leader_load, true_legit_leader_load,
			num_teams, max_load):
		return f(total_svr_load, min(legit_svr_load,true_legit_svr_load), true_legit_svr_load,
			total_leader_load, min(legit_leader_load,true_legit_leader_load), true_legit_leader_load,
			num_teams, max_load)
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
		"epsilon_falloff": explore_episodes * episode_length
	}

	# helpers

	initd_host_count = [0]
	initd_switch_count = [0]
	def newNamedHost(**kw_args):
		o = net.addHost("h{}".format(initd_host_count[0]), **kw_args)
		initd_host_count[0] += 1
		return o
	def newNamedSwitch(**kw_args):
		o = net.addSwitch("s{}".format(initd_switch_count[0]), listenPort=7000+initd_switch_count[0], **kw_args)
		initd_switch_count[0] += 1
		return o

	def trackedLink(src, target, extras=None):
		if extras is None:
			extras = linkopts
		l = net.addLink(src, target, **extras)
		return l

	route_commands = [[]]
	switch_sockets = [{}]

	def openSwitchSocket(switch):
		if switch.name in switch_sockets[0]:
			killsock(switch_sockets[0][switch.name])
			
		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		s.connect(("127.0.0.1", switch.listenPort))
		s.sendall(ofpb.ofp_hello(None, None))
		ofpp.parse(s.recv(8))
		switch.control_socket = s

		switch_sockets[0][switch.name] = s
		return s

	def killsock(s):
		try:
			s.shutdown(socket.SHUT_RDWR)
		except:
			pass
		s.close()

	def removeAllSockets():
		for _, sock in switch_sockets[0].viewitems():
			killsock(sock)
		switch_sockets[0] = {}

	def updateOneRoute(switch, cmd_list, msg):
		if not switch.listenPort:
			switch.cmd(*cmd_list)
		else:
			s = (switch_sockets[0][switch.name]
				if switch.name in switch_sockets[0]
				else openSwitchSocket(switch)
			)

			# seems like pipes can randomly break. oops!
			sent = False
			while not sent:
				try:
					s.sendall(msg)
					sent = True
				except:
					s = openSwitchSocket(switch)

	def executeRouteQueue():
		for el in route_commands[0]:
			updateOneRoute(*el)
		route_commands[0] = []

	flow_pdrop_msg = ofpb.ofp_flow_mod(
		None, 0, 0, 0, ofp.OFPFC_ADD,
		0, 0, 1, None, None, None, 0, 1,
		ofpb.ofp_match(None, None, None),
		ofpb.ofp_instruction_actions(ofp.OFPIT_WRITE_ACTIONS, None, [
			# Looks like 29 is the number I picked for Pdrop.
			ofpb._pack("HHI", 29, 8, 0xffffffff),
			ofpb.ofp_action_output(None, 16, 1, 65535)
		])
	)

	def updateUpstreamRoute(switch, out_port=1, ac_prob=0.0):
		# Turn from prob_drop into prob_send!
		prob = 1 - ac_prob
		name = switch.name
		p_drop_num = pdrop(prob)
		p_drop = "" if ac_prob == 0.0 else "probdrop:{},".format(p_drop_num)

		# really lazy -- big one-directional route. But that's all we need for now.
		if not switch.listenPort:
			listenAddr = "unix:/tmp/{}.listen".format(switch.name)
		else:
			listenAddr = "tcp:127.0.0.1:{}".format(switch.listenPort)

		cmd_list = [
			"ovs-ofctl",
			"add-flow",
			listenAddr,
			"actions={}\"{}-eth{}\"".format(p_drop, name, out_port)
		]

		# Try building that message from scratch, here.
		msg = flow_pdrop_msg[:-20] + ofpb._pack("I", p_drop_num) + flow_pdrop_msg[-16:]
		#For now
		#print msg
		
		if alive:
			updateOneRoute(switch, cmd_list, msg)
		else:
			route_commands[0].append((switch, cmd_list, msg))

	def routedSwitch(upstreamNode, **args):
		sw = newNamedSwitch(**args)
		trackedLink(upstreamNode, sw)
		updateUpstreamRoute(sw)
		return sw

	def enactActions(learners, sarsas):
		for (node, sarsa) in zip(learners, sarsas):
			(_, action, _) = sarsa.last_act
			updateUpstreamRoute(node, ac_prob=action)

	def moralise(value, good, max_val=255, no_goods=[0, 255]):
		target_mod = 0 if good else 1
		god_mod = max_val + 1

		if (value % 2) != target_mod:
			value += 1
			value %= god_mod

		if value in no_goods:
			value += 2
			value %= god_mod

		return value		

	def addHosts(extern, hosts_per_learner, hosts_upper):
		host_count = (hosts_per_learner if hosts_per_learner == hosts_upper
			else random.randint(hosts_per_learner, hosts_upper)
		)

		hosts = []

		for i in xrange(host_count):
			new_host = newNamedHost()
			good = random.random() < P_good
			bw = (random.uniform(*(good_range if good else evil_range)))

			link = trackedLink(extern, new_host, {"bw": bw} if (old_style or force_host_tc) else {})

			# Make up a wonderful IP.
			# Last byte => goodness. Even = good.
			ip_bytes = [random.randint(0,0xff) for i in xrange(4)]
			ip_bytes[-1] = moralise(ip_bytes[-1], good)

			ip = "{}.{}.{}.{}".format(*ip_bytes)

			#print ip

			hosts.append(
				(new_host, good, bw, link, ip)
			)
		return hosts

	def makeTeam(parent, inter_count, learners_per_inter, sarsas=[]):
		leader = routedSwitch(parent)

		intermediates = []
		learners = []
		extern_switches = []
		hosts = []

		newSarsas = len(sarsas) == 0

		for i in xrange(inter_count):
			new_interm = routedSwitch(leader)
			intermediates.append(new_interm)

			for j in xrange(learners_per_inter):
				new_learn = routedSwitch(new_interm)

				# Init and pair the actual learning agent here, too!
				# Bootstrapping happens later -- per-episode, in the 0-load state.
				if newSarsas:
					sarsas.append(SarsaLearner(**sarsaParams))
				
				learners.append(new_learn)

				new_extern = routedSwitch(new_learn)
				extern_switches.append(new_extern)

		return (leader, intermediates, learners, extern_switches, hosts, sarsas)

	def makeHosts(team, hosts_per_learner, hosts_upper=None):
		if hosts_upper is None:
			hosts_upper = hosts_per_learner

		(leader, intermediates, learners, extern_switches, hosts, sarsas) = team

		for (host, _, _, link, _) in hosts:
			host.stop()#deleteIntfs=True)
			link.delete()

		new_hosts = []

		for extern in extern_switches:
			new_hosts += addHosts(extern, hosts_per_learner, hosts_upper)

		return (leader, intermediates, learners, extern_switches, new_hosts, sarsas)

	def buildNet(n_teams, team_sarsas=[]):
		server = newNamedHost()
		server_switch = newNamedSwitch()
		core_link = trackedLink(server, server_switch)
		updateUpstreamRoute(server_switch)

		make_sarsas = len(team_sarsas) == 0

		teams = []
		for i in xrange(n_teams):
			t = makeTeam(server_switch, n_inters, n_learners,
				sarsas=[] if make_sarsas else team_sarsas[i])
			trackedLink(server_switch, t[0])
			teams.append(t)
			if make_sarsas: team_sarsas.append(t[-1])

		return (server, server_switch, core_link, teams, team_sarsas)

	def pdrop(prob):
		return int(prob * 0xffffffff)

	### THE EXPERIMENT? ###

	# initialisation
	rewards = []
	good_traffic_percents = []
	total_loads = []

	net = None
	store_sarsas = []
	alive = False

	interrupted = [False]
	def sigint_handle(signum, frame):
		print "Interrupted, cleaning up."
		interrupted[0] = True

	signal.signal(signal.SIGINT, sigint_handle)

	for ep in xrange(episodes):
		Cleanup.cleanup()
		if interrupted[0]:
			break

		initd_switch_count = [0]
		initd_host_count = [0]
		alive = False
		if separate_episodes:
			store_sarsas = []

		print "beginning episode {} of {}".format(ep+1, episodes)

		net = Mininet(link=TCLink)

		# May be useful to keep around
		#net.addController("c0", controller=RemoteController, ip="127.0.0.1", port=6633)

		# build the network model...
		# EVERY TIME, because scorched-earth is the only language mininet speaks
		(server, server_switch, core_link, teams, team_sarsas) = buildNet(n_teams, team_sarsas=store_sarsas)

		tracked_switches = [server_switch] + list(itertools.chain.from_iterable([
			[leader] + intermediates + learners for (leader, intermediates, learners, _, _, _) in teams
		]))

		tracked_interfaces = ["{}-eth1".format(el.name) for el in tracked_switches]

		switch_list_indices = {}
		for i, sw in enumerate(tracked_switches):
			switch_list_indices[sw.name] = i

		# remake/reclassify hosts
		all_hosts = []
		host_procs = []
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
			for (host, good, bw, _, _) in new_hosts:
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
		for (_, _, learners, _, _, sarsas) in teams:
			for (node, sarsa) in zip(learners, sarsas):
				# reset network model to default rules.
				updateUpstreamRoute(node)

				# Assume initial state is all zeroes (new network)
				sarsa.bootstrap(sarsa.to_state(np.zeros(sarsaParams["vec_size"])))
		
		# Update master link's bandwidth limit after hosts init.
		capacity = calc_max_capacity(len(all_hosts))
		if protect_final_hop:
			core_link.intf1.config(bw=capacity)
			core_link.intf2.config(bw=capacity)

		# Track the rewards, total load observed and legit rates per step (split by episode)
		rewards.append([])
		good_traffic_percents.append([])
		total_loads.append([])

		# Begin the new episode!
		net.start()
		alive = True
		executeRouteQueue()

		#net.interact()

		# Spool up the monitoring tool.
		mon_cmd = server_switch.popen(
			["../marl-bwmon/marl-bwmon"] + tracked_interfaces,
			stdin=PIPE,
			stderr=sys.stderr
		)

		# gen traffic at each host. This MUST happen after the bootstrap.
		for (_, _, _, _, hosts, _) in teams:
			for (host, good, bw, link, ip) in hosts:
				cmd = [
					"tcpreplay-edit",
					"-i", host.intfNames()[0],
					"-l", str(0),
					"-S", "0.0.0.0/0:{}/32".format(ip)
				] + (
					[] if old_style else ["-M", str(bw)]
				) + [(good_file if good else bad_file)]
				 
				#host.sendCmd(
				#	*cmd
				#)
				host_procs.append(host.popen(
					cmd, stdin=PIPE, stderr=sys.stderr
				))

		# Let the pcaps come to life.
		time.sleep(0.5)

		last_traffic_ratio = 0.0
		g_reward = 0.0

		for i in xrange(episode_length):
			# May need to early exit
			if interrupted[0]:
				break
			# Make the last actions a reality!
			for (_, _, learners, _, _, sarsas) in teams:
				enactActions(learners, sarsas)

			#presleep = time.time()

			# Wait, somehow
			time.sleep(dt)

			#postsleep = time.time()

			# Measure good/bad loads!
			mon_cmd.stdin.write("\n")
			mon_cmd.stdin.flush()
			data = mon_cmd.stdout.readline().strip().split(",")
			#print data

			time_ns = int(data[0][:-2])
			load_mbps = [map(
					lambda bytes: (8000*float(bytes))/time_ns,
					el.strip().split(" ")
				) for el in data[1:]
			]

			total_mbps = [good+bad for (good, bad) in load_mbps]

			last_traffic_ratio = min(load_mbps[0][0]/bw_all[0], 1.0)
			if not (i % 10): print "\titer {}/{}, good:{}".format(i, episode_length, last_traffic_ratio)

			for team_no, (leader, intermediates, learners, _, _, sarsas) in enumerate(teams):
				team_true_loads = bw_teams[team_no]

				leader_index = switch_list_indices[leader.name]

				# Compute reward!
				reward = safe_reward_func(reward_func, total_mbps[0], load_mbps[0][0], bw_all[0],
					total_mbps[leader_index], load_mbps[leader_index][0], bw_teams[team_no][0],
					n_teams, capacity)

				g_reward = safe_reward_func(std_marl, total_mbps[0], load_mbps[0][0], bw_all[0],
					total_mbps[leader_index], load_mbps[leader_index][0], bw_teams[team_no][0],
					n_teams, capacity)

				for learner_no, (node, sarsa) in enumerate(zip(learners, sarsas)):
					# Encode state (as seen by this learner)
					important_indices = [switch_list_indices[name] for name in [
						intermediates[learner_no/n_learners].name, node.name
					]]

					state_vec = np.array([total_mbps[index] for index in [0, leader_index]+important_indices])
					state = sarsa.to_state(state_vec)

					# Learn!
					sarsa.update(state, reward)

			good_traffic_percents[-1].append(last_traffic_ratio)
			rewards[-1].append(g_reward)
			total_loads[-1].append(total_mbps[0])

		print "good:", last_traffic_ratio, ", g_reward:", g_reward

		# End this monitoring instance.
		mon_cmd.stdin.close()

		removeAllSockets()

		for proc in host_procs:
			proc.terminate()

		host_procs = []

		net.stop()

		store_sarsas = team_sarsas

	# Okay, done!
	# Run interesting stats stuff here? Just save the results? SAVE THE LEARNED MODEL?!
	return (rewards, good_traffic_percents, total_loads, store_sarsas, random.getstate())
