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
import itertools
import math
import networkx as nx
import numpy as np
import os
import random
from sarsa import SarsaLearner
import signal
import socket
import struct
from subprocess import PIPE, Popen
import sys
import time

controller_build_port = 6666

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
	):

	linkopts["bw"] = manual_early_limit

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

	# helpers

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
		(lhs,) = struct.unpack("I", socket.inet_aton(ip))
		(rhs,) = struct.unpack("I", socket.inet_aton(subnet))
		return struct.pack("I", lhs & rhs)

	def internal_choose_group(group, ip="10.0.0.1", subnet="255.255.255.0"):
		return ofpb.ofp_flow_mod(
			None, 0, 0, 0, ofp.OFPFC_ADD,
			0, 0, 1, None, None, None, 0, 1,
			ofpb.ofp_match(ofp.OFPMT_OXM, None, [
				ofpm.build(None, ofp.OFPXMT_OFB_ETH_TYPE, False, 0, 0x0800, None),
				ofpm.build(None, ofp.OFPXMT_OFB_IPV4_DST, True, 0, netip(ip, subnet), socket.inet_aton(subnet))
			]),
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

	def updateUpstreamRoute(switch, out_port=1, ac_prob=0.0):
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
			msg = internal_choose_group(int(ac_prob * 10))

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

	def enactActions(learners, sarsas):
		for (node, sarsa) in zip(learners, sarsas):
			(_, action, _) = sarsa.last_act
			a = action if override_action is None else override_action
			updateUpstreamRoute(node, ac_prob=a)

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

		core_link = trackedLink(server, server_switch)#, port_dict=port_dict)
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

		tracked_switches = [server_switch] + list(itertools.chain.from_iterable([
			[leader] + intermediates + learners for (leader, intermediates, learners, _, _, _) in teams
		]))

		tracked_interfaces = ["{}-eth1".format(el.name) for el in tracked_switches]

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
			["../marl-bwmon/marl-bwmon"] + tracked_interfaces,
			stdin=PIPE,
			stderr=sys.stderr
		)

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
						#bw_headers = udp_h_size * (10.0**(6.0 - rate_const))
						#bw_pad = bw_MB - bw_headers
						#expand = max(0, int(bw_pad / (10.0 ** (6.0 - rate_const))))
						target = 1500.0
						s = target - udp_h_size
						#now, find delay in microseconds between packets of size 1500
						interval_s = target/bw_MB
						interval_us = int(interval_s * (10.0 ** 6.0))
						print interval_s
						#print "chose", expand, "to add onto the message length: target", bw, "seeing", (udp_h_size + expand) * (10**(-rate_const) * 8.0), "from", ip
						#print "chose", interval_us, "to send pkts: target", bw, "seeing", (target * (interval_us / (10.0**12.0)) * 8.0), "from", ip
	
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

						print cmd
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
		if with_ratio:
			# FIXME: broken with new stats.
			mon_cmd.stdin.write("\n")
			mon_cmd.stdin.flush()
			data = mon_cmd.stdout.readline().strip().split(",")

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

		for i in xrange(episode_length):
			# May need to early exit
			if interrupted[0]:
				break
			# Make the last actions a reality!
			for (_, _, learners, _, _, sarsas) in teams:
				enactActions(learners, sarsas)

			presleep = time.time()

			# Wait, somehow
			time.sleep(dt)

			postsleep = time.time()

			#print postsleep - presleep

			# Measure good/bad loads!
			mon_cmd.stdin.write("\n")
			mon_cmd.stdin.flush()
			data = mon_cmd.stdout.readline().strip().split(",")

			time_ns = int(data[0][:-2])
			unfused_load_mbps = [map(
					lambda bytes: (8000*float(bytes))/time_ns,
					el.strip().split(" ")
				) for el in data[1:]
			]
			load_mbps = [(ig+og, ib+ob) for ((ig, ib), (og, ob)) in zip(unfused_load_mbps[::2], unfused_load_mbps[1::2])]

			# This now has format: inbound, outbound...
			unfused_total_mbps = [good+bad for (good, bad) in unfused_load_mbps]
			total_mbps = [good + bad for (good, bad) in load_mbps]

			# FIXME: need to make this more general to apply to teams etc...
			reward_src = load_mbps[0]
			if reward_direction == "in":
				reward_src = unfused_load_mbps[0]
			elif reward_direction == "out":
				reward_src = unfused_load_mbps[1]

			last_traffic_ratio = min(load_mbps[0][0]/bw_all[0], 1.0)
			if not (i % 10): print "\titer {}/{}, good:{}, load:{}".format(i, episode_length, last_traffic_ratio, total_mbps[0])

			for team_no, (leader, intermediates, learners, _, _, sarsas) in enumerate(teams):
				team_true_loads = bw_teams[team_no]

				leader_index = switch_list_indices[leader.name]

				# Compute reward!
				reward = safe_reward_func(reward_func, total_mbps[0], load_mbps[0][0], bw_all[0],
					total_mbps[leader_index], load_mbps[leader_index][0], bw_teams[team_no][0],
					n_teams, capacity, ratio)

				g_reward = safe_reward_func(std_marl, total_mbps[0], load_mbps[0][0], bw_all[0],
					total_mbps[leader_index], load_mbps[leader_index][0], bw_teams[team_no][0],
					n_teams, capacity, ratio)

				for learner_no, (node, sarsa) in enumerate(zip(learners, sarsas)):
					# Encode state (as seen by this learner)

					# Start time of action computation
					s_t = time.time()

					important_indices = [switch_list_indices[name] for name in [
						intermediates[learner_no/n_learners].name, node.name
					]]

					state_vec = np.array([total_mbps[index] for index in [0, leader_index]+important_indices])
					state = sarsa.to_state(state_vec)

					# Learn!
					sarsa.update(state, reward)

					# End time.
					e_t = time.time()

					action_comps[-1].append((i, e_t - s_t))

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
			pass#print sar[0].values

	# Okay, done!
	# Run interesting stats stuff here? Just save the results? SAVE THE LEARNED MODEL?!
	return (rewards, good_traffic_percents, total_loads, store_sarsas, random.getstate(), action_comps)
