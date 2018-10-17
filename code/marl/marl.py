from mininet.topo import Topo
from mininet.node import OVSSwitch, RemoteController, Switch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.net import Mininet
from mininet.clean import Cleanup

import twink.ofp5 as ofp
import twink.ofp5.build as ofpb
import twink.ofp5.oxm as ofpm
import twink.ofp5.parse as ofpp

from contextlib import closing
import cPickle as pickle
import errno
import itertools
import math
import networkx as nx
import numpy as np
import os
import random
from sarsa import SarsaLearner
import select
import signal
import socket
import struct
from subprocess import PIPE, Popen
import sys
import time

controller_build_port = 6666
stats_port = 9932

def marlExperiment(
		linkopts = {
			#"bw": 10,
			"delay": 10,
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
		break_equal = False,

		model = "tcpreplay",
		submodel = None,

		use_controller = False,
		moralise_ips = True,

		dt = 0.001,

		# These should govern tc on the links at various points in the network.
		#
		# Final hop is just what you'd think, old_style governs
		# whether sender rates are mediated by tcpreplay or by tc on the link
		# over from said host.
		old_style = False,
		force_host_tc = False,
		protect_final_hop = True,

		with_ratio = False,
		override_action = None,
		manual_early_limit = None,
		estimate_const_limit = False,

		rf = "ctl",

		rand_seed = 0xcafed00d,
		rand_state = None,
		force_cmd_routes = False,

		rewards = [],
		good_traffic_percents = [],
		total_loads = [],
		store_sarsas = [],
		action_comps = [],

		reward_direction = "in",
		state_direction = "in",
		actions_target_flows = False,

		bw_mon_socketed = False,
		unix_sock = True,
		print_times = False,
		record_times = False,

		contributors = None,
		restrict = None,
	):

	linkopts_core = linkopts
	linkopts_core["bw"] = manual_early_limit

	# Use any predetermined random state.
	if rand_state is not None:
		random.setstate(rand_state)
	elif rand_seed is not None:
		random.seed(rand_seed)

	c0 = RemoteController("c0", ip="127.0.0.1", port=6633)
	class MaybeControlledSwitch(OVSSwitch):
		def __init__(self, name, **params):
			OVSSwitch.__init__(self, name, **params)
			self.controlled = False

		def start(self, controllers):
			return OVSSwitch.start(self, self._controller_list())

		def _controller_list(self):
			return [c0] if use_controller and self.controlled else []

	if max_bw is None:
		max_bw = n_teams * n_inters * n_learners * host_range[1] * evil_range[1]

	if bad_file is None:
		bad_file = good_file

	if calc_max_capacity is None:
		calc_max_capacity = lambda hosts: good_range[1]*hosts + 2

	if manual_early_limit is None and estimate_const_limit:
		linkopts_core["bw"] = calc_max_capacity(
			host_range[1] * n_teams * n_inters * n_learners
		)

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
			num_teams, max_load, ratio):
		return f(total_svr_load, min(legit_svr_load,true_legit_svr_load), true_legit_svr_load,
			total_leader_load, min(legit_leader_load,true_legit_leader_load), true_legit_leader_load,
			num_teams, max_load*ratio)
	# gen

	sarsaParams = {
		"max_bw": max_bw,
		"vec_size": 4,
		"actions": pdrop_magnitudes,
		"epsilon": epsilon,
		"learn_rate": alpha,
		"discount": discount,
		"break_equal": break_equal,
		# "tile_c": 16,
		# "tilings_c": 3,
		# "default_q": 0,
		"epsilon_falloff": explore_episodes * episode_length
	}

	if actions_target_flows:
		# order of the features:
		#  ip, last_act, len, size, cx_ratio,
		#  mean_iat, delta_in, delta_out
		sarsaParams["extended_mins"] = [
			0.0, 0.0, 0.0, 0.0, 0.0,
			0.0, -50.0, -50.0
		]

		sarsaParams["extended_maxes"] = [
			4294967296.0, 0.9, 2000.0, float(10 * (1024 ** 2)), 1.0,
			10000.0, 50.0, 50.0
		]

		if restrict is not None:
			sarsaParams["vec_size"] = len(restrict)
			for prop_name in ["extended_mins", "extended_maxes"]:
				old = sarsaParams[prop_name]
				# TODO: work to allow selection of 0--4
				sarsaParams[prop_name] = [old[i-4] for i in restrict]
		else:
			sarsaParams["vec_size"] += len(sarsaParams["extended_maxes"])


	# helpers

	def flow_to_state_vec(flow_set):
		return [
			float(flow_set["ip"]),
			float(flow_set["last_act"]) / 10.0,
			# conert from ns to ms
			flow_set["length"] / 1000000,
			flow_set["size"],
			flow_set["cx_ratio"],
			flow_set["mean_iat"],
			flow_set["delta_in"],
			flow_set["delta_out"],
		]

	initd_host_count = [1]
	initd_switch_count = [1]
	next_ip = [1]

	def newNamedHost(**kw_args):
		o = net.addHost("h{}".format(initd_host_count[0]), **kw_args)
		initd_host_count[0] += 1
		return o
	def newNamedSwitch(**kw_args):
		o = net.addSwitch("s{}".format(initd_switch_count[0]), listenPort=7000+initd_switch_count[0], **kw_args)
		initd_switch_count[0] += 1
		return o

	def assignIP(node):
		node.setIP("10.0.0.{}".format(next_ip[0]), 24)
		next_ip[0] += 1

	def map_link(port_dict, n1, n2):
		def label(node):
			if isinstance(node, Switch):
				return node.dpid
			else:
				return node.IP()

		def dict_link(s_l, t_l):
			if s_l not in port_dict:
				port_dict[s_l] = {}

			d = port_dict[s_l]
			if t_l not in d:
				port_dict[s_l][t_l] = len(d) + 1

		s_label = label(n1)
		t_label = label(n2)

		dict_link(s_label, t_label)
		dict_link(t_label, s_label)

	def trackedLink(src, target, extras=None, port_dict=None):
		if extras is None:
			extras = linkopts
		l = net.addLink(src, target, **extras)

		if port_dict is not None:
			map_link(port_dict, src, target)
		return l

	#def limit_bw(link, bw):
	#	cmds = ['%s qdisc change dev %s root handle 5:0 htb default 1',
	#		'%s class add dev %s parent 5:0 classid 5:1 htb ' +
	#		'rate %fMbit burst 15k' % bw ]
	#	errs = [link.tc(cmd) for cmd in cmds]

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
		if force_cmd_routes or not switch.listenPort:
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
					#print ofpp.parse(s.recv(4096)) 
				except:
					s = openSwitchSocket(switch)

	def executeRouteQueue():
		for el in route_commands[0]:
			updateOneRoute(*el)
		route_commands[0] = []

	def pdrop(prob):
		return int(prob * 0xffffffff)

	def netip(ip, subnet):
		(lhs,) = struct.unpack("I", socket.inet_aton(ip)) if isinstance(ip, str) else (ip,)
		(rhs,) = struct.unpack("I", socket.inet_aton(subnet))
		return struct.pack("I", lhs & rhs)

	def internal_choose_group(group, ip="10.0.0.1", subnet="255.255.255.0", target_ip=None):
		importance = 1 if target_ip is None else 0
		priority = 1 if target_ip is None else 2

		source_matcher = [] if target_ip is None else [ofpm.build(None, ofp.OFPXMT_OFB_IPV4_SRC, True, 0, netip(target_ip, "255.255.255.255"), socket.inet_aton("255.255.255.255"))]

		return ofpb.ofp_flow_mod(
			None, 0, 0, 0, ofp.OFPFC_ADD,
			0, 0, priority, None, None, None, 0, importance,
			ofpb.ofp_match(ofp.OFPMT_OXM, None, [
				ofpm.build(None, ofp.OFPXMT_OFB_ETH_TYPE, False, 0, 0x0800, None),
				ofpm.build(None, ofp.OFPXMT_OFB_IPV4_DST, True, 0, netip(ip, subnet), socket.inet_aton(subnet))
			] + source_matcher),
			ofpb.ofp_instruction_actions(ofp.OFPIT_APPLY_ACTIONS, None, [
				ofpb.ofp_action_group(None, 8, group)
			])
		)

	flow_pdrop_msg = [""]
	flow_upstream_msg = [""]
	flow_gselect_msg = [""]
	flow_outbound_msg = [""]
	flow_outbound_flood = [""]
	flow_arp_upcall = [""]
	flow_group_msgs = [[]]

	def compute_msg(ip="10.0.0.1", subnet="255.255.255.0",
			out_port=1, away_port=2):
		flow_pdrop_msg[0] = ofpb.ofp_flow_mod(
			None, 0, 0, 0, ofp.OFPFC_ADD,
			0, 0, 1, None, None, None, 0, 1,
#			ofpb.ofp_match(None, None, None),
			ofpb.ofp_match(ofp.OFPMT_OXM, None, [
				ofpm.build(None, ofp.OFPXMT_OFB_ETH_TYPE, False, 0, 0x0800, None),
				#ofpm.build(None, ofp.OFPXMT_OFB_IPV4_DST, False, 0, socket.inet_aton(ip), None)
				ofpm.build(None, ofp.OFPXMT_OFB_IPV4_DST, True, 0, netip(ip, subnet), socket.inet_aton(subnet))
			]),
			ofpb.ofp_instruction_actions(ofp.OFPIT_WRITE_ACTIONS, None, [
				# Looks like 29 is the number I picked for Pdrop.
				ofpb._pack("HHI", 29, 8, 0xffffffff),
				ofpb.ofp_action_output(None, 16, out_port, 65535)
				#ofpb.ofp_action_output(None, 16, ofp.OFPP_FLOOD, 65535)
			])
		)

		flow_arp_upcall[0] = ofpb.ofp_flow_mod(
			None, 0, 0, 0, ofp.OFPFC_ADD,
			0, 0, 1, None, None, None, 0, 1,
			ofpb.ofp_match(ofp.OFPMT_OXM, None, [
				ofpm.build(None, ofp.OFPXMT_OFB_ETH_TYPE, False, 0, 0x0806, None),
			]),
			ofpb.ofp_instruction_actions(ofp.OFPIT_WRITE_ACTIONS, None, [
				ofpb.ofp_action_output(None, 16, ofp.OFPP_CONTROLLER, 65535)
			])
		)

		groups = []
		
		for i in xrange(10):
			#calc pdrop number
			prob = 1.0 - (i/10.0)
			p_drop_num = pdrop(prob)

			# For select group, weight MUST be zero.
			groups.append(ofpb.ofp_group_mod(
				None, ofp.OFPGC_ADD, ofp.OFPGT_INDIRECT, i,
				ofpb.ofp_bucket(None, 0, ofp.OFPP_ANY, ofp.OFPG_ANY, [
					# Looks like 29 is the number I picked for Pdrop.
					ofpb._pack("HHI", 29, 8, p_drop_num),
					ofpb.ofp_action_output(None, 16, out_port, 65535)
				])
			))

		flow_group_msgs[0] = groups

		flow_gselect_msg[0] = internal_choose_group(0, ip=ip, subnet=subnet)

		flow_outbound_msg[0] = ofpb.ofp_flow_mod(
			None, 0, 0, 0, ofp.OFPFC_ADD,
			0, 0, 0, None, None, None, 0, 1,
			ofpb.ofp_match(None, None, None),
			ofpb.ofp_instruction_actions(ofp.OFPIT_WRITE_ACTIONS, None, [
				ofpb.ofp_action_output(None, 16, away_port, 65535)
			])
		)

		flow_outbound_flood[0] = ofpb.ofp_flow_mod(
			None, 0, 0, 0, ofp.OFPFC_ADD,
			0, 0, 0, None, None, None, 0, 1,
			ofpb.ofp_match(None, None, None),
			ofpb.ofp_instruction_actions(ofp.OFPIT_WRITE_ACTIONS, None, [
				ofpb.ofp_action_output(None, 16, ofp.OFPP_FLOOD, 65535)
			])
		)

		flow_upstream_msg[0] = ofpb.ofp_flow_mod(
			None, 0, 0, 0, ofp.OFPFC_ADD,
			0, 0, 1, None, None, None, 0, 1,
			ofpb.ofp_match(ofp.OFPMT_OXM, None, [
				ofpm.build(None, ofp.OFPXMT_OFB_ETH_TYPE, False, 0, 0x0800, None),
				ofpm.build(None, ofp.OFPXMT_OFB_IPV4_DST, True, 0, netip(ip, subnet), socket.inet_aton(subnet))
			]),
			ofpb.ofp_instruction_actions(ofp.OFPIT_WRITE_ACTIONS, None, [
				ofpb.ofp_action_output(None, 16, out_port, 65535)
			])
		)

	compute_msg()

	def prepLearner(switch, out_port=1, ac_prob=0.0):
		if switch.controlled:
			return

		cmd_list = []

		# send group+bucket instantiations,
		# also the base rules (internal dst -> G0, external -> outwards port=2)
		for msg in flow_group_msgs[0] + flow_gselect_msg + flow_outbound_msg:
			if alive:
				updateOneRoute(switch, cmd_list, msg)
			else:
				route_commands[0].append((switch, cmd_list, msg))

	def prepExternal(switch, out_port=1, ac_prob=0.0):
		if switch.controlled:
			return

		cmd_list = []

		# send group+bucket instantiations,
		# also the base rules (internal dst -> G0, external -> outwards port=2)
		for msg in flow_arp_upcall + flow_upstream_msg + flow_outbound_flood:
			if alive:
				updateOneRoute(switch, cmd_list, msg)
			else:
				route_commands[0].append((switch, cmd_list, msg))

	def updateUpstreamRoute(switch, out_port=1, ac_prob=0.0, target_ip=None):
		if switch.controlled:
			return

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
		if not use_controller:
			if p_drop_num == 0xffffffff:
				msg = flow_upstream_msg[0]
			else:
				# Try building that message from scratch, here.
				copy_msg = flow_pdrop_msg[0]

				msg = copy_msg[:-20] + ofpb._pack("I", p_drop_num) + copy_msg[-16:]
		else:
			cmd_list = []
			msg = internal_choose_group(int(ac_prob * 10), target_ip=target_ip)

		if alive:
			updateOneRoute(switch, cmd_list, msg)
		else:
			route_commands[0].append((switch, cmd_list, msg))

	def routedSwitch(upstreamNode, variant, *args, **kw_args):
		sw = newNamedSwitch(*args)
		trackedLink(upstreamNode, sw, **kw_args)
		if not use_controller:
			updateUpstreamRoute(sw)
		elif variant == 0:
			#controlled
			sw.controlled = True
		elif variant == 1:
			#learner
			prepLearner(sw)
			updateUpstreamRoute(sw)
		elif variant == 2:
			#external
			prepExternal(sw)	
			sw.controlled = True
		return sw

	def enactActions(learners, sarsas, flow_action_sets):
		if actions_target_flows:
			intime = time.time()
			for (node, sarsa, maps) in zip(learners, sarsas, flow_action_sets):
				for ip, state in maps.iteritems():
					(_, action, _) = state
					a = action if override_action is None else override_action
					updateUpstreamRoute(node, ac_prob=sarsa.actions[a], target_ip=ip)
			outtime = time.time()
			if print_times:
				print "do_acs:", outtime-intime
		else:
			for (node, sarsa) in zip(learners, sarsas):
				(_, action) = sarsa.last_act
				a = action if override_action is None else override_action
				updateUpstreamRoute(node, ac_prob=sarsa.actions[a])

	def moralise(value, good, max_val=255, no_goods=[0, 255]):
		target_mod = 0 if good else 1
		god_mod = max_val + 1

		if moralise_ips and (value % 2) != target_mod:
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
			good = random.random() < P_good
			bw = (random.uniform(*(good_range if good else evil_range)))
			print "drew: good={}, bw={}".format(good, bw)

			# Make up a wonderful IP.
			# Last byte => goodness. Even = good.

			# The spectre of classful routing still haunts us all.
			lims = [0xdf,0xff,0xff,0xff]
			ip_bytes = [random.randint(0,lim) for lim in lims]
			# 10.*.*.* is a/our PRIVATE space.
			while ip_bytes[0] == 10 or ip_bytes[0] == 0:
				ip_bytes[0] = random.randint(1, lims[0])
			ip_bytes[-1] = moralise(ip_bytes[-1], good)

			ip = "{}.{}.{}.{}".format(*ip_bytes)

			new_host = newNamedHost(ip="{}.{}.{}.{}/24".format(*ip_bytes))
			link = trackedLink(extern, new_host, {"bw": bw} if (old_style or force_host_tc) else {})

			new_host.setIP(ip, 24)

			hosts.append(
				(new_host, good, bw, link, ip)
			)
		return hosts

	def makeTeam(parent, inter_count, learners_per_inter, sarsas=[], graph=None,
			ss_label=None, port_dict=None):
		leader = routedSwitch(parent, 0, port_dict=port_dict)

		def add_to_graph(parent, new_child):
			label = (None, new_child.dpid)
			if graph is not None and parent is not None:
				graph.add_edge(parent, label)
			return label

		leader_label = add_to_graph(ss_label, leader)

		intermediates = []
		learners = []
		extern_switches = []
		hosts = []

		newSarsas = len(sarsas) == 0

		for i in xrange(inter_count):
			new_interm = routedSwitch(leader, 0, port_dict=port_dict)
			intermediates.append(new_interm)
			inter_label = add_to_graph(leader_label, new_interm)

			for j in xrange(learners_per_inter):
				new_learn = routedSwitch(new_interm, 1, port_dict=port_dict)
				_ = add_to_graph(inter_label, new_learn)

				# Init and pair the actual learning agent here, too!
				# Bootstrapping happens later -- per-episode, in the 0-load state.
				if newSarsas:
					sarsas.append(SarsaLearner(**sarsaParams))
				
				learners.append(new_learn)

				new_extern = routedSwitch(new_learn, 2)
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
		server_switch.controlled = use_controller

		port_dict = {}

		core_link = trackedLink(server, server_switch, extras=linkopts_core)#, port_dict=port_dict)
		updateUpstreamRoute(server_switch)
		assignIP(server)
		map_link(port_dict, server, server_switch)

		make_sarsas = len(team_sarsas) == 0

		G = nx.Graph()
		server_label = ((server.IP(), server.MAC()), None)
		switch_label = (None, server_switch.dpid)
		G.add_edge(server_label, switch_label)

		teams = []
		for i in xrange(n_teams):
			t = makeTeam(server_switch, n_inters, n_learners,
				sarsas=[] if make_sarsas else team_sarsas[i],
				graph=G,
				ss_label=switch_label,
				port_dict=port_dict)
			# this doesn't need to even be here
			#trackedLink(server_switch, t[0], port_dict=)
			teams.append(t)
			if make_sarsas: team_sarsas.append(t[-1])

		return (server, server_switch, core_link, teams, team_sarsas, G, port_dict)

	### THE EXPERIMENT? ###

	# initialisation

	net = None
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

		initd_switch_count = [1]
		initd_host_count = [1]
		alive = False
		if separate_episodes:
			store_sarsas = []

		print "beginning episode {} of {}".format(ep+1, episodes)

		net = Mininet(link=TCLink, switch=MaybeControlledSwitch)

		# build the network model...
		# EVERY TIME, because scorched-earth is the only language mininet speaks
		(server, server_switch, core_link, teams, team_sarsas, graph, port_dict) = buildNet(n_teams, team_sarsas=store_sarsas)

		learner_pos = {}
		learner_name = []
		tracked_switches = [server_switch] + list(itertools.chain.from_iterable([
			[leader] + intermediates + learners for (leader, intermediates, learners, _, _, _) in teams
		]))

		for (_, _, learners, _, _, _) in teams:
			for learner in learners:
				learner_pos[learner.name] = len(learner_name)
				learner_name.append(learner.name)

		tracked_interfaces = [
			"{}{}-eth1".format(
				"!" if actions_target_flows and el.name in learner_pos else "",
				el.name,
			) for el in tracked_switches
		]

		switch_list_indices = {}
		for i, sw in enumerate(tracked_switches):
			switch_list_indices[sw.name] = i

		# setup the controller, if required...
		ctl_proc = None
		controller = None
		if use_controller:
			# host the daemon, queue conns
			#print "I have good reason to believe that I'm creating ryu."
			ctl_proc = Popen(
				[
					"ryu-manager", "controller.py",
					"--verbose"
				],
				stdin=PIPE,
				stderr=sys.stderr
			)

			apsp = dict(nx.all_pairs_shortest_path(graph))

			# classify nodes before building table info for the controller
			ips = []
			dpids = []
			inner_host_macs = {}
			for node in graph.nodes():
				(maybe_ip, maybe_dpid) = node
				if maybe_ip is not None:
					(ip, mac) = maybe_ip
					ips.append(node)
					inner_host_macs[ip] = mac
				if maybe_dpid is not None:
					dpids.append(node)

			def hard_label(node):
				(left, right) = node
				return left[0] if right is None else right

			# for each dpid, find the port which is closest to each IP
			entry_map = {}
			for dnode in dpids:
				(_, dpid) = dnode
				entry_map[dpid] = {}
				for inode in ips:
					((ip, _), _) = inode
					path = apsp[dnode][inode]
					port = port_dict[dpid][hard_label(path[1])]
					# (port_no, adjacent?)
					entry_map[dpid][ip] = (port, len(path)==2)

			# handle those conns
			# now send computed stuff to ctl...
			sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			try:
				try:
					socket.SO_REUSEPORT
				except AttributeError:
					pass
				else:
					sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

				sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
				sock.bind(("127.0.0.1", controller_build_port))
				sock.listen(1)
				data_sock = sock.accept()[0]
				try:
					# pickle, send its length, send the pickle...
					pickle_str = pickle.dumps((entry_map, inner_host_macs))
					data_sock.sendall(struct.pack("!Q", len(pickle_str)))
					data_sock.sendall(pickle_str)
				finally:
					data_sock.close()
			finally:
				sock.close()

			# mininet will automatically link switches to a controller, if it
			# exists and is registered.
			#controller = net.addController("c0", controller=RemoteController, ip="127.0.0.1", port=6633)

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
				#updateUpstreamRoute(node)

				# Assume initial state is all zeroes (new network)
				sarsa.bootstrap(sarsa.to_state(np.zeros(sarsaParams["vec_size"])))
		
		# Update master link's bandwidth limit after hosts init.
		capacity = calc_max_capacity(len(all_hosts))
		print capacity, bw_all
		if protect_final_hop:
			core_link.intf1.config(bw=float(capacity))
			core_link.intf2.config(bw=float(capacity))
			pass

		# Track the rewards, total load observed and legit rates per step (split by episode)
		rewards.append([])
		good_traffic_percents.append([])
		total_loads.append([])
		action_comps.append([])

		# pre-setup (i.e. controller config...)
		net.build()

		# Begin the new episode!
		net.start()

		# What do the hosts believe their IP to be?
		# i.e. this won't set correctly until the net has started.
		for (h, i) in [(host, ip) for (host, _, _, _, ip) in all_hosts] + [(server, server.IP())]:
			h.setIP(i, 24)
			h.setDefaultRoute(h.intf())

		alive = True
		executeRouteQueue()

		# Spool up the monitoring tool.
		mon_cmd = server_switch.popen(
			["../marl-bwmon/marl-bwmon"]
			+ (["-s"] if bw_mon_socketed else [])
			+ tracked_interfaces,
			stdin=PIPE,
			stderr=sys.stderr
		)
		# IF USING SOCKET TO TALK...
		# this should save a lot on I/O + BW.
		#struct FlowMeasurement {
		#	int64_t flow_length;
		#	uint64_t size_in;
		#	uint64_t size_out;
		#	uint64_t delta_in;
		#	uint64_t delta_out;
		#	uint64_t packets_in_count;
		#	uint64_t packets_out_count;
		#	float packets_in_mean;
		#	float packets_in_variance;
		#	float packets_out_mean;
		#	float packets_out_variance;
		#	float iat_mean;
		#	float iat_variance;
		#	uint32_t ip;
		#};
		# repack into...
		# props: (
		#  len_ns, sz_in, sz_out, [0-2]
		#  wnd_sz_in, wnd_sz_out, [3-4]
		#  pkt_in_sz_mean, pkt_in_sz_var, pkt_in_count, [5-7]
		#  pkt_out_sz_mean, pkt_out_sz_var, pkt_out_count, [8-10]
		#  wnd_iat_mean, wnd_iat_var [11-12]
		# )
		bw_sock = None
		if bw_mon_socketed:
			# need to mix this with connection management
			# i.e. open a socket out here, have this function make use of it...
			# remember to close this at the end...!
			#bw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			#try:
			#	socket.SO_REUSEPORT
			#except AttributeError:
			#	pass
			#else:
			#	bw_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

			#bw_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
			time.sleep(0.5)
			if unix_sock:
				bw_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
				bw_sock.connect("bwmon-sock")
			else:
				bw_sock = socket.create_connection(("127.0.0.1", stats_port))
			bw_sock.setblocking(0)

			# "flows" should be an array of u32s
			sz_packer = struct.Struct("!I")
			ip_packer = struct.Struct("=I")
			time_packer = struct.Struct("=q")
			bytes_packer = struct.Struct("=Q")
			fm_packer = struct.Struct("=q6Q6fI4x")
			def ask_stats(flows, n_ifs, n_agents):
				# to the socket, send |flows| as u32
				# as well as each flow ip, as a u32.
				intime = time.time()
				bw_sock.sendall(sz_packer.pack(len(flows)))
				flow_data = ""
				for flow in flows:
					flow_data += ip_packer.pack(flow)
				outtime = time.time()
				bw_sock.sendall(flow_data)
				if print_times:
					print "interlude:", outtime - intime

				recvd = ""
				def read_n(n, recvd):
					while len(recvd) < n:
						try:
							t = bw_sock.recv(4096)
						except socket.error, e:
							err = e.args[0]
							if err == errno.EAGAIN or err == errno.EWOULDBLOCK:
								continue
							else:
								print "Life sucks"
								sys.exit(1)
						else:
							recvd += t
					return recvd

				# read time in ns...
				len_ns = 8
				recvd = read_n(len_ns, recvd)
				(time_ns,) = time_packer.unpack(recvd[:len_ns])
				recvd = recvd[len_ns:]

				# then, read n_if * (u64 * 2)
				#  [goodx2 per if], [badx2 per if]
				list_sz = n_ifs * 8 * 2
				full = list_sz * 2
				recvd = read_n(full, recvd)

				def mbpsify(bts):
					return 8000*float(bts)/time_ns

				goods = []
				bads = []
				for i in xrange(n_ifs * 2 * 2):
					index = i * 8
					(val,) = bytes_packer.unpack(recvd[index: index+8])
					if i < (n_ifs * 2):
						goods.append(mbpsify(val))
					else:
						bads.append(mbpsify(val))
				unfused_load_mbps = [pair for pair in zip(goods, bads)]
				recvd = recvd[full:]

				parsed_flows = []

				for i in xrange(n_agents):
					# read a u32 (network order),
					# then read that many size 88 structs
					len_u32 = 4
					recvd = read_n(len_u32, recvd)
					(n_flow_entries,) = sz_packer.unpack(recvd[:len_u32])
					recvd = recvd[len_u32:]
					# (ip, stats)
					l_flows = []
					stat_struct_len = 88
					stat_struct_len_nopad = stat_struct_len - 4
					for i in xrange(n_flow_entries):
						recvd = read_n(stat_struct_len, recvd)
						datas = list(fm_packer.unpack(
							recvd[:stat_struct_len]
						))
						recvd = recvd[stat_struct_len:]
						if datas[-1] != 0:
							l_flows.append(
								(datas[-1], tuple(
									datas[0:5] + datas[7:9] + [datas[5]] +
									datas[9:11] + [datas[6]] + datas[11:13]
								))
							)
					parsed_flows.append(l_flows)
				# repack it as the rest of the model expects
				return (time_ns, unfused_load_mbps, parsed_flows)
		else:
			# no granularity, get all flow info
			def ask_stats(_flows, _n_ifs, _n_agents):
				# Measure good/bad loads!
				mon_cmd.stdin.write("\n")
				mon_cmd.stdin.flush()
				data = mon_cmd.stdout.readline().strip().split(",")

				flow_stat_str = mon_cmd.stdout.readline().strip()
				flow_stat_break = flow_stat_str.split("]")
				split_stats = [s.strip().split("[")[-1] for s in flow_stat_break if len(s) > 0]
				# now split into flow-keys. (ip, ...)(ip, ...)
				almost_subs = [s.split(")") for s in split_stats if len(s) > 0]
				subs = []
				for set_str in almost_subs:
					if len(set_str) == 0:
						continue
					subs.append([a.split("(")[-1].split(",") for a in set_str])

				# (ip, props)
				# props: (len_ns, sz_in, sz_out, wnd_sz_in, wnd_sz_out, pkt_in_sz_mean, pkt_in_sz_var, pkt_in_count, pkt_out_sz_mean, pkt_out_sz_var, pkt_out_count, wnd_iat_mean, wnd_iat_var)
				parsed_flows = []

				for l in subs:
					if len(l) == 0:
						continue

					layer = []
					for e in l:
						if len(e[0]) == 0:
							continue

						sublayer = []
						for item in e[1:]:
							sublayer.append(float(item))
						if e[0] != "0.0.0.0":
							ip_bytes = socket.inet_pton(socket.AF_INET, e[0])
							layer.append((struct.unpack("I", ip_bytes)[0], sublayer))
						
					parsed_flows.append(layer)

				time_ns = int(data[0][:-2])

				def mbpsify(bts):
					return 8000*float(bts)/time_ns

				unfused_load_mbps = [map(
						mbpsify,
						el.strip().split(" ")
					) for el in data[1:]
				]

				return (time_ns, unfused_load_mbps, parsed_flows)

		# spool up server if need be
		server_proc = None

		if model == "nginx":
			cmd = [
				"nginx",
				"-p", "../traffic-host",
				"-c", "h1.conf",
			]

			server_proc = server.popen(
				cmd, stdin=PIPE, stderr=sys.stderr
			)

		if model == "nginx":
			#net.interact()
                        pass

		server_ip = server.IP()

		# gen traffic at each host. This MUST happen after the bootstrap.
		for (_, _, _, _, hosts, _) in teams:
			for (host, good, bw, link, ip) in hosts:
				if model == "tcpreplay":
					cmd = [
						"tcpreplay-edit",
						"-i", host.intfNames()[0],
						"-l", str(0),
						"-S", "0.0.0.0/0:{}/32".format(ip),
						"-D", "0.0.0.0/0:{}/32".format(server_ip)
					] + (
						[] if old_style else ["-M", str(bw)]
					) + [(good_file if good else bad_file)]
				elif model == "nginx":
					if submodel == "http" or (submodel is None and good):
						cmd = [
							"../traffic-host/target/release/traffic-host",
							str(bw),
							# temp/testing
							"-s", "10.0.0.1/gcc-8.2.0.tar.gz"
						]
					elif submodel == "udp-flood" or (submodel is None and not good):
						#rate_const = 3.0 if not good else 4.0
						udp_h_size = 28.0
						bw_MB = (bw / 8.0) * (10.0**6.0)
						target = 1500.0
						s = target - udp_h_size
						#now, find delay in microseconds between packets of size 1500
						interval_s = target/bw_MB
						interval_us = int(interval_s * (10.0 ** 6.0))
						print interval_s
	
						cmd = [
							"hping3",
							"--udp",
							#"-i", "u{}".format(rate_const),
							#"-d", str(expand),
							"-i", "u{}".format(interval_us),
							"-d", str(int(s)),
							#"-a", ip,
							"-I", "h",
							"10.0.0.1"
						]
				else:
					cmd = []

				if len(cmd) > 0:
					host_procs.append(host.popen(
						cmd, stdin=sys.stdout, stderr=sys.stderr
					))

		# Let the pcaps come to life.
		time.sleep(3)

		# Now establish the true maximum throughput
		ratio = 1.0
		if with_ratio and not bw_mon_socketed:
			mon_cmd.stdin.write("\n")
			mon_cmd.stdin.flush()
			data = mon_cmd.stdout.readline().strip().split(",")

			_flow_stat_str = mon_cmd.stdout.readline()

			time_ns = int(data[0][:-2])
			load_mbps = [map(
					lambda bytes: (8000*float(bytes))/time_ns,
					el.strip().split(" ")
				) for el in data[1:]
			]

			observed = load_mbps[0][0] + load_mbps[0][1]
			print observed, bw_all[2]
			ratio = observed / bw_all[2]

			print "new limit is:", ratio*capacity, "from", capacity

			if protect_final_hop:
				core_link.intf1.config(bw=ratio*capacity)
				core_link.intf2.config(bw=ratio*capacity)

		last_traffic_ratio = 0.0
		g_reward = 0.0

		if ep > 0:
			#net.interact()
			pass

		learner_stats = [{} for _ in learner_pos]
		learner_traces = [{} for _ in learner_pos]
		flows_to_query = []

		for i in xrange(episode_length):
			# May need to early exit
			if interrupted[0]:
				break
			# Make the last actions a reality!
			for (_, _, learners, _, _, sarsas) in teams:
				enactActions(learners, sarsas, learner_traces)

			if i == 10:
				#net.interact()
				#quit()
				pass

			presleep = time.time()

			# Wait, somehow
			time.sleep(dt)

			postsleep = time.time()

			#print postsleep - presleep
			preask = time.time()
			(time_ns, unfused_load_mbps, parsed_flows) = ask_stats(flows_to_query, len(tracked_interfaces), len(learner_pos))
			postask = time.time()
			if print_times:
				print "total:", postask - preask
			# REMOVE
			#print ["{}:{}".format(a,hex(a)) for a in flows_to_query]
			#for a in parsed_flows:
			#	for b in a:
			#		print "{}".format(hex(b[0]))

			def mbpsify(bts):
					return 8000*float(bts)/time_ns

			load_mbps = [(ig+og, ib+ob) for ((ig, ib), (og, ob)) in zip(unfused_load_mbps[::2], unfused_load_mbps[1::2])]

			# This now has format: inbound, outbound...
			unfused_total_mbps = [good+bad for (good, bad) in unfused_load_mbps]
			total_mbps = [good + bad for (good, bad) in load_mbps]

			def get_data(n):
				reward_src = load_mbps[n]
				if reward_direction == "in":
					reward_src = unfused_load_mbps[2*n]
				elif reward_direction == "out":
					reward_src = unfused_load_mbps[2*n + 1]
				return reward_src

			def get_total(n):
				reward_src = total_mbps[n]
				if reward_direction == "in":
					reward_src = unfused_total_mbps[2*n]
				elif reward_direction == "out":
					reward_src = unfused_total_mbps[2*n + 1]
				return reward_src

			l_cap = (2.0 if state_direction == "fuse" else 1.0) * capacity

			last_traffic_ratio = min(get_data(0)[0]/bw_all[0], 1.0)
			if not (i % 10): print "\titer {}/{}, good:{}, load:{:.2f} ({:.2f},{:.2f})".format(i, episode_length, last_traffic_ratio, total_mbps[0], *unfused_total_mbps[0:2])

			flows_to_query = []
			for team_no, (leader, intermediates, learners, _, _, sarsas) in enumerate(teams):
				team_true_loads = bw_teams[team_no]

				leader_index = switch_list_indices[leader.name]

				# Compute reward!
				reward = safe_reward_func(reward_func, get_total(0), get_data(0)[0], bw_all[0],
					get_total(leader_index), get_data(leader_index)[0], bw_teams[team_no][0],
					n_teams, l_cap, ratio)

				g_reward = safe_reward_func(std_marl, get_total(0), get_data(0)[0], bw_all[0],
					get_total(leader_index), get_data(leader_index)[0], bw_teams[team_no][0],
					n_teams, l_cap, ratio)

				intime = time.time()
				for learner_no, (node, sarsa) in enumerate(zip(learners, sarsas)):
					important_indices = [switch_list_indices[name] for name in [
						intermediates[learner_no/n_learners].name, node.name
					]]

					#state_vec = np.array([total_mbps[index] for index in [0, leader_index]+important_indices])
					state_vec = [total_mbps[index] for index in [0, leader_index]+important_indices]
					# if on hard mode, do some other stuff instead.
					if actions_target_flows:
						# props: (
						#  len_ns, sz_in, sz_out, [0-2]
						#  wnd_sz_in, wnd_sz_out, [3-4]
						#  pkt_in_sz_mean, pkt_in_sz_var, pkt_in_count, [5-7]
						#  pkt_out_sz_mean, pkt_out_sz_var, pkt_out_count, [8-10]
						#  wnd_iat_mean, wnd_iat_var [11-12]
						# )
						l_index = learner_no + (team_no * len(learners))
						flow_space = learner_stats[l_index]
						flow_traces = learner_traces[l_index]
						flows_seen = parsed_flows[l_index]

						# TODO: strip old entries?

						for (ip, props) in flows_seen:
							s_t = time.time()
							flows_to_query.append(ip)

							if ip not in flow_space:
								flow_space[ip] = {
									"ip": ip,
									"last_act": 0,
									"last_rate_in": -1.0,
									"last_rate_out": -1.0
								}
							l = flow_space[ip]

							l["cx_ratio"] = min(*props[1:3]) / max(*props[1:3])
							l["length"] = props[0]
							l["size"] = props[1] + props[2]
							l["mean_iat"] = props[11]
							observed_rate_in = mbpsify(props[3])
							observed_rate_out = mbpsify(props[4])

							if l["last_rate_in"] < 0.0:
								l["last_rate_in"] = observed_rate_in
								l["last_rate_out"] = observed_rate_out
							l["delta_in"] = observed_rate_in - l["last_rate_in"]
							l["delta_out"] = observed_rate_out - l["last_rate_out"]

							total_vec = state_vec + flow_to_state_vec(l)

							# TODO: work with contributors etc in here...
							# Each needs its own view of the state...
							# (and specifies its restriction thereof)
							# Combine these to get a vector of likelihoods,
							# get the highest-epsilon to calculate the action.
							# Then update each model with the TRUE action chosen.
							tx_vec = total_vec if restrict is None else [total_vec[i] for i in restrict]
							print total_vec, tx_vec
							state = sarsa.to_state(np.array(tx_vec))

							# if there was an earlier decision made on this flow, then update the past state estimates associated.
							# Compute and store the intended update for each flow.
							if ip in flow_traces:
								(l_action, ac_vals) = sarsa.update(state, reward, flow_traces[ip])
							else:
								l_action = sarsa.bootstrap(state)

							flow_traces[ip] = sarsa.last_act

							# TODO: maybe only update this whole thing if we're choosing to examine this flow.
							l["last_act"] = l_action 
							l["last_rate_in"] = observed_rate_in
							l["last_rate_out"] = observed_rate_out

							flow_space[ip] = l
							# print l
							# End time.
							e_t = time.time()

							#print "computed action: it took {}s".format(e_t - s_t)

							if record_times:
								action_comps[-1].append((i, e_t - s_t))

							learner_traces[l_index] = flow_traces
					else:
						# Encode state (as seen by this learner)

						# Start time of action computation
						s_t = time.time()

						state = sarsa.to_state(np.array(state_vec))

						# Learn!
						sarsa.update(state, reward)

						# End time.
						e_t = time.time()

						if record_times:
							action_comps[-1].append((i, e_t - s_t))

				outtime = time.time()
				if print_times:
					print "choose_acs:", outtime-intime

			good_traffic_percents[-1].append(last_traffic_ratio)
			rewards[-1].append(g_reward)
			total_loads[-1].append(total_mbps[0])

			zeroed = len(total_loads[-1]) > 0
			for element in total_loads[-1][-3:]:
				zeroed &= (element == 0.0)

			absurd = total_loads[-1][-1] >= 2 * capacity

			# test behaviour: if last 3 are 0 OR we're 2x max, interact.
			if zeroed or absurd:
				#print total_loads[-1][-3:], capacity
				#print load_mbps
				#net.interact()
				pass

		print "good:", last_traffic_ratio, ", g_reward:", g_reward, ", selected:", reward

		#print action_comps[-1]
		# End this monitoring instance.
		mon_cmd.stdin.close()
		#net.interact()

		removeAllSockets()
		if bw_sock is not None:
			bw_sock.shutdown(socket.SHUT_RDWR)
			bw_sock.close()

		if server_proc is not None:
			server_proc.terminate()
		if ctl_proc is not None:
			#print "I have good reason to believe that I'm killing ryu."
			ctl_proc.terminate()
		for proc in host_procs:
			proc.terminate()

		host_procs = []
		server_proc = None
		ctl_proc = None

		net.stop()

		store_sarsas = team_sarsas
		next_ip = [1]

		for sar in store_sarsas:
			#print sar[0].values
			pass

	# Okay, done!
	# Run interesting stats stuff here? Just save the results? SAVE THE LEARNED MODEL?!
	return (rewards, good_traffic_percents, total_loads, store_sarsas, random.getstate(), action_comps)
