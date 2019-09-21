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
from sarsa import SarsaLearner, QLearner
import select
import signal
import socket
from spf import *
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

		topol = "tree",
		ecmp_servers = 8,
		ecmp_k = 4,

		explore_episodes = 80000,
		episodes = 1000,#100000
		episode_length = 5000,#1000
		separate_episodes = False,

		max_bw = None,
		pdrop_magnitudes = [0.1*n for n in xrange(10)],

		alpha = 0.05,
		epsilon = 0.3,
		discount = 0,
		break_equal = None,

		algo = "sarsa",
		trace_decay = 0.0,
		trace_threshold = 0.0001,
		use_path_measurements = True,

		model = "tcpreplay",
		submodel = None,
		rescale_opus = False,
		mix_model = None,

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
		# Can set to "no", "udp", "always"
		prevent_smart_switch_recording = "udp",
		# FIXME: these two flags ae incompatible
		record_times = False,
		record_deltas_in_times = False,

		contributors = [],
		restrict = None,

		single_learner = False,
		single_learner_ep_scale = True,

		spiffy_mode = False,

		randomise = False,
		randomise_count = None,
		randomise_new_ip = False,

		split_codings = False,
		extra_codings = [],
		feature_max = 12,
		combine_with_last_action = [12, 13, 14, 15, 16, 17, 18, 19],
		strip_last_action = True,

		explore_feature_isolation_modifier = 1.0,
		explore_feature_isolation_duration = 5,
		always_include_global = True,
		always_include_bias = True,

		trs_maxtime = None,
		reward_band = 1.0,

		spiffy_but_bad = False,
		spiffy_act_time = 5.0,
		# 24--192 hosts, pick accordingly.
		spiffy_max_experiments = 16,
		spiffy_min_experiments = 1,
		spiffy_pick_prob = 0.2,
		spiffy_drop_rate = 0.15,
		spiffy_traffic_dir = "in",
		spiffy_mbps_cutoff = 0.1,
		spiffy_expansion_factor = 5.0,

		broken_math = False,
		num_drop_groups = 20,
	):

	agent_classes = {
		"sarsa": SarsaLearner,
		"q": QLearner,
	}
	AgentClass = agent_classes[algo]

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
			host_range[1] * n_teams * n_inters * n_learners / (1.0 if topol != "ecmp" else float(ecmp_servers))
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
			num_teams, reward_band*max_load*ratio)
	# gen

	# change the state machine we get to roll with...
	if spiffy_mode or spiffy_but_bad:
		AcTrans = SpfMachine
		aset = range(3)
		default_machine_state = 1
	else:
		AcTrans = MarlMachine
		aset = pdrop_magnitudes
		default_machine_state = 0

	if spiffy_but_bad:
		actions_target_flows = True

	if single_learner and single_learner_ep_scale:
		explore_episodes *= float(n_teams * n_inters * n_learners)

	def random_target(dests):
		target_dest = dests[0] if len(dests) == 1 else dests[random.randint(0, len(dests)-1)]
		return target_dest[0][0]

	def th_cmd(dests, bw, target_ip=None):
		if target_ip is None:
			target_ip = random_target(dests)
		#print "aiming for http://{}/".format(target_ip)

		return [
			"../traffic-host/target/release/traffic-host",
			str(bw),
		] + (
			["-s", "http://{}/gcc-8.2.0.tar.gz".format(target_ip)] if not randomise else \
			[
				"-r",
				"-l", "../traffic-host/htdoc-deps.ron",
				"-s", "http://{}/".format(target_ip)
			]
		) + (
			[] if randomise_count is None else ["-c", str(randomise_count)]
		)
	total_thing = [0.0]
	def opus_cmd(dests, bw, host, target_ip=None):
		ip_list = [d[0][0] for d in dests]

		# Do we want multiple calls?
		# The stats observed show that flows occupy (in expectation)
		# ~52kbps (median 49.906) with the below settings. If flows were constantly submitting,
		# we'd see ~85kbps (median 97) accounting for a target 96kbps (w/ some per-server deviation)
		divisor = 1.0
		if rescale_opus:
			ub = host_range[1]
			# lerp between some observations at differing n
			pt = float(max(0, ub - 2)) / 14.0
			divisor = 0.6 + pt * (0.45 - 0.6)
			print "rescaled to", divisor
		flow_bw = 52.39456 / (divisor * 1024.0) # to mbps.
		subclient_count = int(math.ceil(max(1.0, bw / flow_bw)))
		total_thing[0] += flow_bw * subclient_count
		print subclient_count, total_thing

		return [
			"../opus-voip-traffic/target/release/opus-voip-traffic",
			#"../opus-voip-traffic/target/debug/opus-voip-traffic",
			"-i", ",".join(ip_list),
			"-m", "5000",
			"-c", str(subclient_count),
			"-b", "../opus-voip-traffic",
			"--ip-strategy", "even",
			#"--iface", "{}-eth0".format(host.name),
			"--constant",
			"--refresh",
		]

	break_equal = (spiffy_mode) if break_equal is None else break_equal

	sarsaParams = {
		"max_bw": max_bw,
		"vec_size": 4,
		"actions": aset,
		"epsilon": epsilon,
		"learn_rate": alpha,
		"discount": discount,
		"break_equal": break_equal,
		# "tile_c": 16,
		# "tilings_c": 3,
		# "default_q": 0,
		"epsilon_falloff": explore_episodes * episode_length,
		"AcTrans": AcTrans,
		"trace_decay": trace_decay,
		"trace_threshold": trace_threshold,
		"broken_math": broken_math,
		"always_include_bias": always_include_bias,
	}

	if actions_target_flows:
		# order of the features:
		#  ip, last_act, len, size, cx_ratio,
		#  mean_iat, delta_in, delta_out,
		#  pkt_in_count, pkt_out_count,
		#  pkt_in_wnd_count, pkt_out_wnd_count,
		#  mean_bpp_in, mean_bpp_out,
		#  delta_in_wnd, delta_out_wnd,
		sarsaParams["extended_mins"] = [
			0.0, 0.0, 0.0, 0.0, 0.0,
			0.0, -50.0, -50.0,
			0.0, 0.0,
			0.0, 0.0,
			0.0, 0.0,
			-50.0, -50.0,
		][0:feature_max-4]

		sarsaParams["extended_maxes"] = [
			4294967296.0, 1.0, 2000.0, float(10 * (1024 ** 2)), 1.0,
			10000.0, 50.0, 50.0,
			7000.0, 7000.0,
			2000.0, 2000.0,
			1560.0, 1560.0,
			50.0, 50.0,
		][0:feature_max-4]

		if restrict is not None:
			sarsaParams["vec_size"] = len(restrict)
			for prop_name in ["extended_mins", "extended_maxes"]:
				old = sarsaParams[prop_name]
				# TODO: work to allow selection of 0--4
				sarsaParams[prop_name] = [old[i-4] for i in restrict]
		else:
			sarsaParams["vec_size"] += len(sarsaParams["extended_maxes"])

		if not split_codings:
			sarsaParams["tc_indices"] = [np.arange(sarsaParams["vec_size"])]
		else:
			sarsaParams["tc_indices"] = [np.arange(4)] + [[i] for i in xrange(4, sarsaParams["vec_size"])]

			# Okay, index of last_action is 2 after the last global datum in the feature vector.
			# combine_with_last_action, strip_last_action, use_path_measurements
			# Note: its index in the feature vector is 5, its position in the list of tc indices is 2.
			if combine_with_last_action is not None:
				for index in combine_with_last_action:
					# subtract (global_actions - 1) to move to correct position
					f_index = index - 3
					if f_index < len(sarsaParams["tc_indices"]):
						sarsaParams["tc_indices"][f_index] += [5]

			if strip_last_action:
				del sarsaParams["tc_indices"][2]

		sarsaParams["tc_indices"] += extra_codings


	# helpers

	def flow_to_state_vec(flow_set):
		return [
			float(flow_set["ip"]),
			float(flow_set["last_act"]),
			# conert from ns to ms
			flow_set["length"] / 1000000,
			flow_set["size"],
			flow_set["cx_ratio"],
			flow_set["mean_iat"],
			flow_set["delta_in"],
			flow_set["delta_out"],
			flow_set["pkt_in_count"],
			flow_set["pkt_out_count"],
			flow_set["pkt_in_wnd_count"],
			flow_set["pkt_out_wnd_count"],
			flow_set["mean_bpp_in"],
			flow_set["mean_bpp_out"],
			flow_set["delta_in"],
			flow_set["delta_out"],
		]

	def combine_flow_vecs(fv1, fv2):
		# Some of these we want to flat-out overwrite
		# some of these we want to meaningfully combine.
		# i.e. combining pkt_in_wnds might lead to crazy skew
		# if we don't combine it with timing info.
		in_count = float(fv1[10] + fv2[10])
		out_count = float(fv1[11] + fv2[11])
		fv1_in_weight = float(fv1[10])
		fv2_in_weight = float(fv2[10])
		fv1_out_weight = float(fv1[11])
		fv2_out_weight = float(fv2[11])

		return [
			# take CURRENT global state
			fv2[0],
			fv2[1],
			fv2[2],
			fv2[3],
			# ip and last_action should NOT change.
			fv2[4],
			fv2[5],
			# length, size take max
			max(fv1[6], fv2[6]),
			max(fv1[7], fv2[7]),
			# take newest cx
			fv2[8],
			#rescale IATs (in)
			fv2[9] if in_count == 0.0 else (fv1_in_weight * fv1[9] + fv2_in_weight * fv2[9]) / in_count,
			# sum deltas
			# FIXME: this makes no sense. Why am I summing these? These seem to have predictive power, tho.
			# NOTE: just use deltas in set mode as another 2 entries to the feature vec?
			# I realise now that this is computing the current delta from the INITIAL MEASUREMENNT.
			fv1[10] + fv2[10],
			fv1[11] + fv2[11],
			# take newest on all counts - don't fuse window pkt counts
			fv2[12],
			fv2[13],
			fv2[14],
			fv2[15],
			# rescale mean bpps
			fv2[16] if in_count == 0.0 else (fv1_in_weight * fv1[16] + fv2_in_weight * fv2[16]) / in_count,
			fv2[17] if out_count == 0.0 else (fv1_out_weight * fv1[17] + fv2_out_weight * fv2[17]) / out_count,
			# per-window rate deltas
			fv2[18],
			fv2[19],
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

	def updateOneRoute(switch, cmd_list, msg, needs_check=False):
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
				except:
					s = openSwitchSocket(switch)
			if needs_check:
				print ofpp.parse(s.recv(4096))

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

	def internal_choose_group(group, ip="10.0.0.1", subnet="255.255.255.0", target_ip=None, force_old=None):
		importance = 1 if target_ip is None else 0
		priority = 1 if target_ip is None else 2

		source_matcher = [] if target_ip is None else [ofpm.build(None, ofp.OFPXMT_OFB_IPV4_SRC, True, 0, netip(target_ip, "255.255.255.255"), socket.inet_aton("255.255.255.255"))]

		if force_old is not None:
			return ofpb.ofp_flow_mod(
				None, 0, 0, 0, ofp.OFPFC_ADD,
				0, 0, priority, None, None, None, 0, importance,
				ofpb.ofp_match(ofp.OFPMT_OXM, None, [
					ofpm.build(None, ofp.OFPXMT_OFB_ETH_TYPE, False, 0, 0x0800, None),
					ofpm.build(None, ofp.OFPXMT_OFB_IPV4_DST, True, 0, netip(ip, subnet), socket.inet_aton(subnet))
				] + source_matcher),
				ofpb.ofp_instruction_actions(ofp.OFPIT_APPLY_ACTIONS, None, [
					ofpb._pack("HHI", 29, 8, force_old),
					ofpb.ofp_action_output(None, 16, 1, 65535)
				])
			)
		else:
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

	def ip_masker_message(new_ip, old_ip, subnet="255.255.255.255"):
		importance = 0
		priority = 1

		txd_old = netip(old_ip, subnet)
		txd_new = netip(new_ip, subnet)
		txd_sub = socket.inet_aton(subnet)

		# rewrite dst, rewrite src
		return ofpb.ofp_flow_mod(
			None, 0, 0, 0, ofp.OFPFC_ADD,
			0, 0, priority, None, None, None, 0, importance,
			ofpb.ofp_match(ofp.OFPMT_OXM, None, [
				ofpm.build(None, ofp.OFPXMT_OFB_ETH_TYPE, False, 0, 0x0800, None),
				ofpm.build(None, ofp.OFPXMT_OFB_IPV4_SRC, True, 0, txd_old, txd_sub)
			]),
			ofpb.ofp_instruction_actions(ofp.OFPIT_APPLY_ACTIONS, None, [
				ofpb.ofp_action_set_field(None, 8, ofpm.build(None, ofp.OFPXMT_OFB_IPV4_SRC, False, 0, txd_new)),
				ofpb.ofp_action_output(None, 16, ofp.OFPP_CONTROLLER, 65535)
			])
		)

	flow_pdrop_msg = [""]
	flow_upstream_msg = [""]
	flow_upstream_t1_msg = [""]
	flow_gselect_msg = [""]
	flow_outbound_msg = [""]
	flow_outbound_flood = [""]
	flow_arp_upcall = [""]
	flow_miss_next_table = [""]
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

		flow_miss_next_table[0] = ofpb.ofp_flow_mod(
			None, 0, 0, 0, ofp.OFPFC_ADD,
			0, 0, 0, None, None, None, 0, 1,
			ofpb.ofp_match(ofp.OFPMT_OXM, None, [
				#ofpm.build(None, ofp.OFPXMT_OFB_ETH_TYPE, False, 0, 0x0806, None),
			]),
			ofpb.ofp_instruction_goto_table(None, None, 1)
		)

		groups = []

		for i in xrange(num_drop_groups):
			#calc pdrop number
			prob = 1.0 - (i/float(num_drop_groups))
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

		flow_upstream_t1_msg[0] = ofpb.ofp_flow_mod(
			None, 0, 0, 1, ofp.OFPFC_ADD,
			0, 0, 0, None, None, None, 0, 1,
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

		# Need to find what the default degree of punishment for a flow is...
		# THis is contingent on the flow state machine's initial, well, state.
		default_machine = AcTrans()
		ac = default_machine.action()

		if spiffy_but_bad:
			ac = 0.0#spiffy_drop_rate

		p_drop_num = pdrop(1-ac)

		#local_gselect_msg = flow_gselect_msg
		local_gselect_msg = [internal_choose_group(0, force_old=p_drop_num)]

		# send group+bucket instantiations,
		# also the base rules (internal dst -> G0, external -> outwards port=2)
		for msg in flow_group_msgs[0] + local_gselect_msg + flow_outbound_msg:
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
		for msg in flow_arp_upcall + flow_upstream_t1_msg + flow_outbound_flood + flow_miss_next_table:
			if alive:
				updateOneRoute(switch, cmd_list, msg)
			else:
				route_commands[0].append((switch, cmd_list, msg))

	def prepSpiffyBridge(switch, mac_of_interest, out_port=1, ac_prob=0.0):
		if switch.controlled:
			return

		cmd_list = []

		# Need to add a high-prio match for the switch's MAC address too...
		# Otherwise the ARP replies from the main body of the network get caught in
		# limbo.
		msgs = [
			# put the MAC matcher in here
			ofpb.ofp_flow_mod(
				None, 0, 0, 0, ofp.OFPFC_ADD,
				0, 0, 1, None, None, None, 0, 1,
				ofpb.ofp_match(ofp.OFPMT_OXM, None, [
					ofpm.build(None, ofp.OFPXMT_OFB_ETH_TYPE, False, 0, 0x0806, None),
					#ofpm.build(None, ofp.OFPXMT_OFB_ETH_DST, False, 0, mac_of_interest, None),
					ofpm.build(None, ofp.OFPXMT_OFB_ARP_OP, False, 0, 2, None),
				]),
				ofpb.ofp_instruction_actions(ofp.OFPIT_WRITE_ACTIONS, None, [
					ofpb.ofp_action_output(None, 16, out_port, 65535)
				])
			)
		]

		msgs += flow_upstream_msg + flow_outbound_msg

		for msg in msgs: 
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
		#print prob, p_drop_num
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
			# remove if groups fixed
			os = p_drop_num # = None
			if target_ip is not None:
				(src, dst) = target_ip
				#print int(ac_prob * 10)
				msg = internal_choose_group(int(ac_prob * num_drop_groups), ip=dst, target_ip=src, force_old=os, subnet="255.255.255.255")
			else:
				msg = internal_choose_group(int(ac_prob * num_drop_groups), target_ip=target_ip, force_old=os)

		if alive:
			updateOneRoute(switch, cmd_list, msg)
		else:
			route_commands[0].append((switch, cmd_list, msg))

	def switch_cmd(switch, cmd_list, msg, needs_check=False):
		if alive:
			updateOneRoute(switch, cmd_list, msg, needs_check)
		else:
			route_commands[0].append((switch, cmd_list, msg))

	def routedSwitch(upstreamNode, variant, *args, **kw_args):
		sw = newNamedSwitch(*args)
		if upstreamNode is not None:
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

	def enactActions(actors, flow_action_sets, vertex_map):
		if actions_target_flows:
			intime = time.time()
			for i, ((node_label, sarsa, _leader), maps) in enumerate(zip(actors, flow_action_sets)):
				node = vertex_map[node_label]
				for ip_pair, state in maps.iteritems():
					(_, action, machine, _, guard) = state

					if not guard[0]:
						continue

					a = action if override_action is None else override_action
					# tx_ac = sarsa.actions[a] if isinstance(a, (int, long)) else a
					tx_ac = machine.action() if isinstance(a, (int, long)) else a
					#tx_ac = 0.0
					#print "agent {}: placing {} in {}".format(i, tx_ac, ip_pair)
					updateUpstreamRoute(node, ac_prob=tx_ac, target_ip=ip_pair)
					guard[0] = False
			outtime = time.time()
			if print_times:
				print "do_acs:", outtime-intime
		else:
			for i, ((node_label, sarsa, _leader), state) in enumerate(zip(actors, flow_action_sets)):
				node = vertex_map[node_label]
				if len(state) == 0:
					action = default_machine_state
				else:
					((_svec, action, _), machine) = state
					action = machine.action()
				a = action if override_action is None else override_action
				tx_ac = sarsa.actions[a] if isinstance(a, (int, long)) else a
				#print "chose {}".format(tx_ac)
				#tx_ac = 0.9
				#print "agent {}: placing {}".format(i, tx_ac)
				updateUpstreamRoute(node, ac_prob=tx_ac)

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

	def genIP(good):
		# The spectre of classful routing still haunts us all.
		lims = [0xdf,0xff,0xff,0xff]
		ip_bytes = [random.randint(0,lim) for lim in lims]
		# 10.*.*.* is a/our PRIVATE space.
		while ip_bytes[0] == 10 or ip_bytes[0] == 0:
			ip_bytes[0] = random.randint(1, lims[0])
		ip_bytes[-1] = moralise(ip_bytes[-1], good)

		ip = "{}.{}.{}.{}".format(*ip_bytes)
		return (ip, ip_bytes)

	def addHosts(extern, extern_no, hosts_per_learner, hosts_upper):
		scaler = 1 if topol == "tree" else (n_teams * n_inters * n_learners) / ((ecmp_k/2)**2)
		host_count = (hosts_per_learner if hosts_per_learner == hosts_upper
			else random.randint(hosts_per_learner, hosts_upper)
		)

		host_count *= scaler

		hosts = []

		for i in xrange(host_count):
			good = random.random() < P_good
			bw = (random.uniform(*(good_range if good else evil_range)))

			# Make up a wonderful IP.
			# Last byte => goodness. Even = good.

			(ip, ip_bytes) = genIP(good)
			print "drew: good={}, bw={}, ip={}".format(good, bw, ip)

			new_host = newNamedHost(ip="{}.{}.{}.{}/24".format(*ip_bytes))
			link = trackedLink(extern, new_host, {"bw": bw} if (old_style or force_host_tc) else {})

			new_host.setIP(ip, 24)

			if mix_model is None:
				sm = submodel
			else:
				draw = random.random()
				total = 0.0
				i = 0
				found_sm = False
				while (not found_sm) and i < len(mix_model):
					(p, m) = mix_model[i]
					total += p
					if draw < total:
						sm = m["submodel"]
						found_sm = True
					i += 1

			hosts.append(
				(new_host, good, bw, link, ip, extern_no, sm)
			)
		return hosts

	def makeTeam(parent, inter_count, learners_per_inter, new_topol_shape, sarsas=[], graph=None,
			ss_label=None, port_dict=None):

		(monitored_links, dests, dest_links, core_links, actors, externals, vertex_map, link_map, spiffy_dest_switches) = new_topol_shape

		def link_in_new_topol(node1, node2, node1_label, node2_label, critical=False):
			link_name = "{}{}-eth1".format(
				"!" if critical else "",
				node2.name,
			)
			index = len(monitored_links)

			vertex_map[node1_label] = node1
			vertex_map[node2_label] = node2
			monitored_links.append(link_name)
			link_map[(node1_label, node2_label)] = index
			link_map[(node2_label, node1_label)] = index

		leader = routedSwitch(parent, 0, port_dict=port_dict)

		def add_to_graph(parent, new_child, label=None):
			if label is None:
				label = (None, new_child.dpid)
			if graph is not None and parent is not None:
				graph.add_edge(parent, label)
			return label

		def link_to_outside(parent):
			return add_to_graph(parent, None, label=(("0.0.0.0", None), None))

		leader_label = add_to_graph(ss_label, leader)
		link_in_new_topol(parent, leader, ss_label, leader_label)

		intermediates = []
		learners = []
		extern_switches = []
		hosts = []

		newSarsas = len(sarsas) == 0

		for i in xrange(inter_count):
			new_interm = routedSwitch(leader, 0, port_dict=port_dict)
			intermediates.append(new_interm)
			inter_label = add_to_graph(leader_label, new_interm)

			# Laziest possible way of doing this. Bad software engineering 101...
			link_in_new_topol(leader, new_interm, leader_label, inter_label)

			for j in xrange(learners_per_inter):
				new_learn = routedSwitch(new_interm, 1, port_dict=port_dict)
				nll = add_to_graph(inter_label, new_learn)
				link_in_new_topol(new_interm, new_learn, inter_label, nll, critical=True)
				_ = link_to_outside(nll)

				# Init and pair the actual learning agent here, too!
				# Bootstrapping happens later -- per-episode, in the 0-load state.
				if newSarsas:
					local_sarsa = AgentClass(**sarsaParams)
					sarsas.append(local_sarsa)
				else:
					local_sarsa = sarsas[(i * inter_count) + j]

				learners.append(new_learn)
				actors.append((nll, local_sarsa, (ss_label, leader_label)))

				new_extern = routedSwitch(new_learn, 2)
				extern_switches.append(new_extern)
				externals.append(new_extern)

		new_topol_shape = (monitored_links, dests, dest_links, core_links, actors, externals, vertex_map, link_map, spiffy_dest_switches)
		return ((leader, intermediates, learners, extern_switches, hosts, sarsas), new_topol_shape)

	def makeHosts(hosts, externs, hosts_per_learner, hosts_upper=None):
		if hosts_upper is None:
			hosts_upper = hosts_per_learner

		for (host, _, _, link, _, _, _) in hosts:
			host.stop()#deleteIntfs=True)
			#link.delete()

		new_hosts = []

		for i, extern in enumerate(externs):
			new_hosts += addHosts(extern, i, hosts_per_learner, hosts_upper)

		return new_hosts

	def controlSwitch(switch, msgs, cmd_list=[]):
		for msg in msgs:
			if alive:
				updateOneRoute(switch, cmd_list, msg)
			else:
				route_commands[0].append((switch, cmd_list, msg))

	def isolateSpiffyFlow(spiffy_dest_switches, flow_ip, dest_ip, isolate_port=3):
		(close_switch, far_switch) = spiffy_dest_switches[dest_ip]
		subnet = "255.255.255.255"

		# on close, match on dest = flow_ip => port 3
		controlSwitch(close_switch, [ofpb.ofp_flow_mod(
			None, 0, 0, 0, ofp.OFPFC_ADD,
			0, 0, 2, None, None, None, 0, 0,
			ofpb.ofp_match(ofp.OFPMT_OXM, None, [
				ofpm.build(None, ofp.OFPXMT_OFB_ETH_TYPE, False, 0, 0x0800, None),
				ofpm.build(None, ofp.OFPXMT_OFB_IPV4_DST, True, 0, netip(flow_ip, subnet), socket.inet_aton(subnet))
			]),
			ofpb.ofp_instruction_actions(ofp.OFPIT_WRITE_ACTIONS, None, [
				ofpb.ofp_action_output(None, 16, isolate_port, 65535)
			])
		)])

		# on far, match on src = flow_ip => port 3
		controlSwitch(far_switch, [ofpb.ofp_flow_mod(
			None, 0, 0, 0, ofp.OFPFC_ADD,
			0, 0, 2, None, None, None, 0, 0,
			ofpb.ofp_match(ofp.OFPMT_OXM, None, [
				ofpm.build(None, ofp.OFPXMT_OFB_ETH_TYPE, False, 0, 0x0800, None),
				ofpm.build(None, ofp.OFPXMT_OFB_IPV4_SRC, True, 0, netip(flow_ip, subnet), socket.inet_aton(subnet))
			]),
			ofpb.ofp_instruction_actions(ofp.OFPIT_WRITE_ACTIONS, None, [
				ofpb.ofp_action_output(None, 16, isolate_port, 65535)
			])
		)])

	def okaySpiffyFlow(spiffy_dest_switches, flow_ip, dest_ip):
		(close_switch, far_switch) = spiffy_dest_switches[dest_ip]
		subnet = "255.255.255.255"

		# on close, match on dest = flow_ip => port 3
		controlSwitch(close_switch, [ofpb.ofp_flow_mod(
			None, 0, 0, 0, ofp.OFPFC_DELETE,
			0, 0, 2, None, None, None, 0, 0,
			ofpb.ofp_match(ofp.OFPMT_OXM, None, [
				ofpm.build(None, ofp.OFPXMT_OFB_ETH_TYPE, False, 0, 0x0800, None),
				ofpm.build(None, ofp.OFPXMT_OFB_IPV4_DST, True, 0, netip(flow_ip, subnet), socket.inet_aton(subnet))
			]),
			None
		)])

		# on far, match on src = flow_ip => port 3
		controlSwitch(far_switch, [ofpb.ofp_flow_mod(
			None, 0, 0, 0, ofp.OFPFC_DELETE,
			0, 0, 2, None, None, None, 0, 0,
			ofpb.ofp_match(ofp.OFPMT_OXM, None, [
				ofpm.build(None, ofp.OFPXMT_OFB_ETH_TYPE, False, 0, 0x0800, None),
				ofpm.build(None, ofp.OFPXMT_OFB_IPV4_SRC, True, 0, netip(flow_ip, subnet), socket.inet_aton(subnet))
			]),
			None
		)])

	def blockSpiffyFlow(spiffy_dest_switches, flow_ip, dest_ip, ingress_switch=None):
		(close_switch, far_switch) = spiffy_dest_switches[dest_ip]
		# FIXME: Unsure whether I should drop here or at network ingress...
		# ingress might be nicer from the perspective of net emulation?
		# but I'm lazy atm...
		subnet = "255.255.255.255"

		# Add an explicit match for the flow, with an empty action list.
		block_messages = [
			ofpb.ofp_flow_mod(
				None, 0, 0, 0, ofp.OFPFC_ADD,
				0, 0, 2, None, None, None, 0, 0,
				ofpb.ofp_match(ofp.OFPMT_OXM, None, [
					ofpm.build(None, ofp.OFPXMT_OFB_ETH_TYPE, False, 0, 0x0800, None),
					ofpm.build(None, ofp.OFPXMT_OFB_IPV4_SRC, True, 0, netip(flow_ip, subnet), socket.inet_aton(subnet))
				]),
				ofpb.ofp_instruction_actions(ofp.OFPIT_CLEAR_ACTIONS, None, None)
			),
			ofpb.ofp_flow_mod(
				None, 0, 0, 0, ofp.OFPFC_ADD,
				0, 0, 2, None, None, None, 0, 0,
				ofpb.ofp_match(ofp.OFPMT_OXM, None, [
					ofpm.build(None, ofp.OFPXMT_OFB_ETH_TYPE, False, 0, 0x0800, None),
					ofpm.build(None, ofp.OFPXMT_OFB_IPV4_DST, True, 0, netip(flow_ip, subnet), socket.inet_aton(subnet))
				]),
				ofpb.ofp_instruction_actions(ofp.OFPIT_CLEAR_ACTIONS, None, None)
			)
		]

		controlSwitch(close_switch, block_messages)
		controlSwitch(far_switch, block_messages)
		if ingress_switch is not None:
			#controlSwitch(ingress_switch, block_messages)
			updateUpstreamRoute(ingress_switch, ac_prob=1, target_ip=(flow_ip, dest_ip))

	def buildTreeNet(n_teams, team_sarsas=[]):
		# names of all internal links
		monitored_links = []
		# dest graph node labels
		dests = []
		# Links relating to each dest.
		dest_links = {}
		# link objects which need limits set.
		core_links = []
		# array of (graph node, sarsa, leader's link points)
		actors = []
		# array of graph nodes (locations to attach hosts)
		externals = []
		# map from graph node -> object
		vertex_map = {}
		# go from (label, label) -> index into link names
		link_map = {}
		# spiffy destinations
		spiffy_dest_switches = {}

		server = newNamedHost()
		server_switch = newNamedSwitch()
		server_switch.controlled = use_controller

		port_dict = {}

		# If we're using SPIFFY-like, we need to put an invisible extra 2 nodes between the server switch and
		# the server (i.e., these do not affect the routing graph).
		if spiffy_but_bad:
			close_switch = newNamedSwitch()
			far_switch = newNamedSwitch()
			close_switch.controlled = False
			far_switch.controlled = False

			# this makes the default path across here in port numbers 1 and 2,
			# and places the TBE link on port 3 for both close/far switches
			last_hop = trackedLink(server, close_switch, extras=linkopts_core)
			normal_link = trackedLink(close_switch, far_switch, extras=linkopts_core)
			core_link = trackedLink(far_switch, server_switch, extras=linkopts_core)
			tbe_link = trackedLink(close_switch, far_switch, extras=linkopts_core)

			core_links.append(normal_link)
			core_links.append(tbe_link)

			# Need to prime close/far to do their job
			mac_of_interest = server.MAC()

			prepSpiffyBridge(close_switch, mac_of_interest)
			prepSpiffyBridge(far_switch, mac_of_interest)
			link_name = "{}-eth1".format(close_switch.name)
		else:
			core_link = trackedLink(server, server_switch, extras=linkopts_core)#, port_dict=port_dict)
			core_links.append(core_link)

			link_name = "{}-eth1".format(server_switch.name)
		monitored_links.append(link_name)

		updateUpstreamRoute(server_switch)
		assignIP(server)
		map_link(port_dict, server, server_switch)

		if spiffy_but_bad:
			spiffy_dest_switches[server.IP()] = (close_switch, far_switch)
		make_sarsas = len(team_sarsas) == 0

		G = nx.Graph()
		server_label = ((server.IP(), server.MAC()), None)
		switch_label = (None, server_switch.dpid)
		G.add_edge(server_label, switch_label)

		dests.append(server_label)
		vertex_map[server_label] = server
		vertex_map[switch_label] = server_switch
		link_map[(server_label, switch_label)] = len(monitored_links) - 1
		link_map[(switch_label, server_label)] = len(monitored_links) - 1

		dest_links[server_label] = [(server_label, switch_label)]

		new_topol_shape = (monitored_links, dests, dest_links, core_links, actors, externals, vertex_map, link_map, spiffy_dest_switches)

		teams = []
		for i in xrange(n_teams):
			(t, n_s) = makeTeam(server_switch, n_inters, n_learners, new_topol_shape,
				sarsas=[] if make_sarsas else team_sarsas[i],
				graph=G,
				ss_label=switch_label,
				port_dict=port_dict,)
			# this doesn't need to even be here
			#trackedLink(server_switch, t[0], port_dict=)
			teams.append(t)
			if make_sarsas: team_sarsas.append(t[-1])
			new_topol_shape = n_s
		print monitored_links
		return (server, server_switch, core_link, teams, team_sarsas, G, port_dict, new_topol_shape)

	def buildEcmpNet(n_teams, team_sarsas=[]):
		# names of all internal links
		monitored_links = []
		# dest graph node labels
		dests = []
		# Links relating to each dest.
		dest_links = {}
		# link objects which need limits set.
		core_links = []
		# array of (graph node, sarsa, leader's link points)
		actors = []
		# array of graph nodes (locations to attach hosts)
		externals = []
		# map from graph node -> object
		vertex_map = {}
		# go from (label, label) -> index into link names
		link_map = {}
		# spiffy destinations
		spiffy_dest_switches = {}

		# FIXME: allow full offline training again, one day...
		make_sarsas = True

		G = nx.Graph()
		port_dict = {}

		# Okay, build something like a fat tree.
		# start w/ the dests...
		servers = []
		for i in xrange(ecmp_servers):
			server = newNamedHost()
			servers.append(server)

		def link_in_new_topol(node1, node2, node1_label, node2_label, critical=False, override_link_name=None):
			link_name = "{}{}-eth{}".format(
				"!" if critical else "",
				node2.name,
				len(node2.ports)-1,
			) if override_link_name is None else override_link_name
			index = len(monitored_links)

			vertex_map[node1_label] = node1
			vertex_map[node2_label] = node2
			monitored_links.append(link_name)
			link_map[(node1_label, node2_label)] = index
			link_map[(node2_label, node1_label)] = index

		def add_to_graph(parent, new_child, label=None):
			if label is None:
				label = (None, new_child.dpid)
			G.add_edge(parent, label)
			return label

		def link_to_outside(parent):
			return add_to_graph(parent, None, label=(("0.0.0.0", None), None))

		# now we need to assign dests to pods
		# there are k/2 hosts per edge node:
		#  there are k/2 edge nodes, and k/2 aggregation in a pod
		max_hosts_per_pod = (ecmp_k**2) / 4
		e_k_2 = ecmp_k/2
		pods_required = int(math.ceil(float(ecmp_servers) / float(max_hosts_per_pod)))
		edge_nodes = []
		for i in xrange(pods_required * e_k_2):
			edge_switch = routedSwitch(None, 0, port_dict=port_dict)
			edge_nodes.append(edge_switch)

			# connect up the edge switch to its intended children
			for dest in servers[i*e_k_2:min(len(servers), (i+1)*e_k_2)]:
				# same trick as in the other topol: insert some dumb-routed nodes between a server and the real
				# (routed) part of the network.
				override_name = None
				if spiffy_but_bad:
					# slight issue, "server_switch" doesn't exist in this topol. is it edge_switch?
					close_switch = newNamedSwitch()
					far_switch = newNamedSwitch()
					close_switch.controlled = False
					far_switch.controlled = False

					# this makes the default path across here in port numbers 0 and 1,
					# and places the TBE link on port 3 for both close/far switches
					last_hop = trackedLink(dest, close_switch, extras=linkopts_core)
					normal_link = trackedLink(close_switch, far_switch, extras=linkopts_core)
					core_link = trackedLink(far_switch, edge_switch, extras=linkopts_core)
					tbe_link = trackedLink(close_switch, far_switch, extras=linkopts_core)

					core_links.append(normal_link)
					core_links.append(tbe_link)
				else:
					core_link = trackedLink(dest, edge_switch, extras=linkopts_core)#, port_dict=port_dict)
					#core_link = trackedLink(server, server_switch, extras=linkopts_core)#, port_dict=port_dict)
					core_links.append(core_link)

				# can't assign IP without a link...
				assignIP(dest)
				server_label = ((dest.IP(), dest.MAC()), None)
				vertex_map[server_label] = dest

				dests.append(server_label)
				map_link(port_dict, dest, edge_switch)
				switch_label = add_to_graph(server_label, edge_switch)

				if spiffy_but_bad:
					mac_of_interest = dest.MAC()

					# Need to prime close/far to do their job
					prepSpiffyBridge(close_switch, mac_of_interest)
					prepSpiffyBridge(far_switch, mac_of_interest)

					spiffy_dest_switches[dest.IP()] = (close_switch, far_switch)
					override_name = "{}-eth1".format(close_switch.name)

				link_in_new_topol(dest, edge_switch, server_label, switch_label, override_link_name=override_name)
				dest_links[server_label] = [(server_label, switch_label)]

		def normal_link(n1, n2, n1_l, critical=False, link=True, **kw_args):
			if link:
				trackedLink(n1, n2, **kw_args)
			n2_l = add_to_graph(n1_l, n2)
			map_link(port_dict, n1, n2)
			link_in_new_topol(n1, n2, n1_l, n2_l, critical)
			return n2_l

		# Now, the aggregation layer.
		# Take k/2 edge_nodes, generate k/2 more aggregation nodes, then do a complete bipartite linking
		agg_nodes = []
		agg_nodes_by_pod = []
		for i in xrange(pods_required * e_k_2):
			#generate, then find the relevant children
			agg_switch = routedSwitch(None, 0, port_dict=port_dict)
			group_index = (i % e_k_2)
			start = i - group_index
			for child in edge_nodes[start:start+e_k_2]:
				normal_link(agg_switch, child, (None, agg_switch.dpid))

			agg_nodes.append(agg_switch)
			if group_index == 0:
				agg_nodes_by_pod.append([])
			agg_nodes_by_pod[-1].append(agg_switch)

		# Now, the core layer. There are (k/2)^2 such nodes.
		# Each core node connects to one element in each pod,
		# before connecting to an agent and then an external node.
		# Worry about agg-core links later...
		newSarsas = len(team_sarsas) == 0

		core_nodes = []
		for i in xrange(e_k_2*e_k_2):
			core_switch = routedSwitch(None, 0, port_dict=port_dict)
			core_nodes.append(core_switch)

			new_learn = routedSwitch(core_switch, 1, port_dict=port_dict)
			nll = normal_link(
				core_switch,
				new_learn,
				(None, core_switch.dpid),
				critical=True, link=False)
			_ = link_to_outside(nll)

			# Init and pair the actual learning agent here, too!
			# Bootstrapping happens later -- per-episode, in the 0-load state.
			if newSarsas:
				local_sarsa = AgentClass(**sarsaParams)
			else:
				local_sarsa = sarsas[i]

			actors.append((nll, local_sarsa, None))

			new_extern = routedSwitch(new_learn, 2)
			externals.append(new_extern)

		# Now, connect each aggregate to its relevant core switches.
		for pod in agg_nodes_by_pod:
			for i, node in enumerate(pod):

				targets = core_nodes[i*e_k_2:(i+1)*e_k_2]
				for core in targets:
					# link node and core
					normal_link(node, core, (None, node.dpid))

		new_topol_shape = (monitored_links, dests, dest_links, core_links, actors, externals, vertex_map, link_map, spiffy_dest_switches)
		return (None, edge_nodes[0], None, None, None, G, port_dict, new_topol_shape)

	if topol == "tree":
		buildNet = buildTreeNet
	elif topol == "ecmp":
		buildNet = buildEcmpNet

	### THE EXPERIMENT? ###

	# initialisation

	net = None
	alive = False

	interrupted = [False]
	def sigint_handle(signum, frame):
		print "Interrupted, cleaning up."
		interrupted[0] = True

	signal.signal(signal.SIGINT, sigint_handle)
	old_hosts = []

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
		(server, server_switch, core_link, teams, team_sarsas, graph, port_dict, new_topol_shape) = buildNet(n_teams, team_sarsas=store_sarsas)
		(monitored_links, dests, dest_links, core_links, actors, externals, vertex_map, link_map, spiffy_dest_switches) = new_topol_shape

		dest_from_ip = {}
		for dest in dests:
			dest_from_ip[dest[0][0]] = dest

		# Compute paths from agents to each dest.
		# Use bigrams to essentially figure out all equal-cost hops.
		dest_map = {}
		for (node, _sarsa, _leader) in actors:
			for dest in dests:
				paths = nx.all_shortest_paths(graph, node, dest)
				for path in paths:
					for (n1, n2) in zip(path, path[1:]):
						# when trying to reach dest from n1, go through n2
						if n1 not in dest_map:
							dest_map[n1] = {}
						if dest not in dest_map[n1]:
							dest_map[n1][dest] = set()
						dest_map[n1][dest].add(n2)

		#print dest_map

		learner_pos = {}
		learner_name = []

		for i, (actor, _sarsa, _leader) in enumerate(actors):
			name = vertex_map[actor].name
			learner_pos[name] = len(learner_name)
			learner_name.append(name)

		# setup the controller, if required...
		ctl_proc = None
		controller = None
		if use_controller:
			# host the daemon, queue conns
			#print "I have good reason to believe that I'm creating ryu."
			ctl_proc = Popen(
				[
					"ryu-manager", "controller.py",
					#"--verbose"
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
					if mac is not None:
						ips.append(node)
						inner_host_macs[ip] = mac
				if maybe_dpid is not None:
					dpids.append(node)

			def hard_label(node):
				(left, right) = node
				return left[0] if right is None else right

			# for each dpid, find the port which is closest to each IP
			entry_map = {}
			escape_map = {}
			port_dest_map = {}
			for dnode in dpids:
				(_, dpid) = dnode
				entry_map[dpid] = {}
				escape_map[dpid] = set()
				# FIXME: adapt for ECMP networks
				for inode in ips:
					((ip, _), _) = inode
					path = apsp[dnode][inode]
					#print dpid, path, ip
					port = port_dict[dpid][hard_label(path[1])]
					# (port_no, adjacent?)
					entry_map[dpid][ip] = (port, len(path)==2)
				# Now, compute the list of escape paths for each node
				# don't really care about how slow this is.
				escape_paths = nx.all_shortest_paths(graph, dnode, (("0.0.0.0", None), None))
				for path in escape_paths:
					target = hard_label(path[1])
					if target == "0.0.0.0":
						continue
					port = port_dict[dpid][target]
					escape_map[dpid].add(port)
				# convert dest_map to go between dpid and hard label...
				if dnode in dest_map:
					port_dest_map[dpid] = {}
					for (dest, next_nodes) in dest_map[dnode].iteritems():
						target = hard_label(dest) # an ip
						port_dest_map[dpid][target] = set()
						for next_node in next_nodes:
							next_l = hard_label(next_node)
							port = port_dict[dpid][next_l]
							port_dest_map[dpid][target].add((port, target==next_l))

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
					pickle_str = pickle.dumps((entry_map, escape_map, inner_host_macs, prevent_smart_switch_recording, port_dest_map))
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
		host_procs = []

		# good, bad, total
		bw_all = [0.0 for i in xrange(3)]
		bw_teams = {}

		# Assign hosts again, and memorise the load they intend to push.
		all_hosts = makeHosts(old_hosts, externals, *host_range)
		old_hosts = all_hosts

		# need to know the intended loads of each class (overall and per-team).
		# can make bw_teams as a dict against leader_node
		# good, bad, total

		# need to remember which hosts correspond to which agent...
		# that agent then has a leader

		host_ip_mac_map = {}

		for (host, good, bw, _, _, extern_no, sm) in all_hosts:
			(lhs,) = struct.unpack("I", socket.inet_aton(host.IP()))
			host_ip_mac_map[lhs] = host.MAC()
			(_a_node, _a_sarsa, a_leader) = actors[extern_no]

			bw_team = None
			if a_leader is not None:
				if a_leader not in bw_teams:
					bw_teams[a_leader] = [0.0 for i in xrange(3)]
				bw_team = bw_teams[a_leader]

			if good:
				if bw_team is not None:
					bw_team[0] += bw
				bw_all[0] += bw
			else:
				if bw_team is not None:
					bw_team[1] += bw
				bw_all[1] += bw

			if bw_team is not None:
				bw_team[2] += bw
			bw_all[2] += bw

		for (node, sarsa, _link_pts) in actors:
			# reset network model to default rules.
			#updateUpstreamRoute(node)

			# Assume initial state is all zeroes (new network)
			sarsa.bootstrap(sarsa.to_state(np.zeros(sarsaParams["vec_size"])))

		# Update master link's bandwidth limit after hosts init.
		capacity = calc_max_capacity(len(all_hosts))/float(len(dests))
		print capacity, bw_all
		if protect_final_hop:
			for core_link in core_links:
				core_link.intf1.config(bw=float(capacity))
				core_link.intf2.config(bw=float(capacity))

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
		for (h, i) in [(host, ip) for (host, _, _, _, ip, _, _) in all_hosts] + [(vertex_map[d], d[0][0]) for d in dests]:
			h.setIP(i, 24)
			h.setDefaultRoute(h.intf())

		alive = True
		executeRouteQueue()

		# Spool up the monitoring tool.
		print monitored_links
		mon_cmd = server_switch.popen(
			["../marl-bwmon/marl-bwmon"]
			+ (["-s"] if bw_mon_socketed else [])
			+ monitored_links,
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
				# internal structure (ext_ip|int_ip,prop1,...|int_ip,prop2,...)
				almost_subs = [s.split(")") if len(s) > 0 else "" for s in split_stats]
				subs = []
				for set_str in almost_subs:
					#if len(set_str) == 0:
						#continue
					#	subs.append([])
					subs.append([a.split("(")[-1].split("|") for a in set_str])

				# (ip, {int_ip: props})
				# props: (len_ns, sz_in, sz_out, wnd_sz_in, wnd_sz_out, pkt_in_sz_mean, pkt_in_sz_var, pkt_in_count, pkt_out_sz_mean, pkt_out_sz_var, pkt_out_count, wnd_iat_mean, wnd_iat_var)
				parsed_flows = []

				for l in subs:
					#if len(l) == 0:
					#	continue

					# layer is all (ip, prop_holder) pairs per agent
					layer = []
					for e in l:
						if len(e[0]) == 0:
							continue

						# e is [ext_ip, flow_key_str, flow_key_str, ...]
						prop_holder = {}
						for flow_prop_str in e[1:]:
							# sublayer is "props"
							prop_str_parts = flow_prop_str.split(",")

							props = []

							#print prop_str_parts
							if prop_str_parts[1] == "":
								continue

							for part in prop_str_parts[1:]:
								props.append(float(part))

							# Keep this as an IP string to aid node lookup later
							prop_holder[prop_str_parts[0]] = props

						if e[0] != "0.0.0.0":
							ip_bytes = socket.inet_pton(socket.AF_INET, e[0])
							layer.append((struct.unpack("I", ip_bytes)[0], prop_holder))
							#if e[3] > 0:
							#	print "culprit: {}, {}".format(e[0], e[3])

					parsed_flows.append(layer)

				time_ns = int(data[0][:-2])

				def mbpsify(bts):
					return 8000*float(bts)/time_ns

				unfused_load_mbps = [map(
						mbpsify,
						el.strip().split(" ")
					) for el in data[1:]
				]

				#print unfused_load_mbps

				return (time_ns, unfused_load_mbps, parsed_flows)

		# spool up server if need be
		server_procs = []

		for i, dest_node in enumerate(dests):
			dest = vertex_map[dest_node]
			if model == "nginx":
				cmds = []
				
				if mix_model is None:
					sms = [submodel]
				else:
					sms = [m["submodel"] for (p, m) in mix_model]
				for sm in sms:
					if sm is None:
						# How to have a sane config for each?
						# Config needs to include the IP so that listening works as intended...
						fname = "temp{}.conf".format(i)

						with open("../traffic-host/"+fname, "w") as f:
							f.write(
								"events {\n" +
								"\tworker_connections 1024;\n" +
								"}\n\n" +
								"http {\n" +
								"\tserver {\n" +
								"\t\tinclude global.conf;\n" +
								"\t\tlisten {}:80;\n".format(dest_node[0][0]) +
								"\t}\n" +
								"}\n"
							)

						cmd = [
							"nginx",
							"-p", "../traffic-host",
							"-c", fname,
						]
					elif submodel == "opus-voip":
						cmd = [
							"../opus-voip-traffic/target/release/opus-voip-traffic",
							"--server",
						]
					cmds.append(cmd)

				for cmd in cmds:
					server_procs.append(dest.popen(
						cmd, stdin=PIPE, stderr=sys.stderr
					))

		if model == "nginx":
			#net.interact()
			pass

		# gen traffic at each host. This MUST happen after the bootstrap.
		#time.sleep(3)
		#if use_controller:
		#	p_cmd = "ping -c 1 " + server_ip
		#	for (_, _, _, _, hosts, _) in teams:
		#		for (host, good, bw, link, ip) in hosts:
		#			host.cmd(p_cmd)

		for (host, good, bw, link, ip, extern_no, sm) in all_hosts:
			target_dest = dests[0] if len(dests) == 1 else dests[random.randint(0, len(dests)-1)]
			target_ip = target_dest[0][0]
			if model == "tcpreplay":
				cmd = [
					"tcpreplay-edit",
					"-i", host.intfNames()[0],
					"-l", str(0),
					"-S", "0.0.0.0/0:{}/32".format(ip),
					"-D", "0.0.0.0/0:{}/32".format(target_ip)
				] + (
					[] if old_style else ["-M", str(bw)]
				) + [(good_file if good else bad_file)]
			elif model == "nginx":
				# TODO: split into good_model and bad_model choices
				if sm == "http" or (sm is None and good):
					cmd = th_cmd(dests, bw, target_ip=target_ip)
				elif sm == "opus-voip" and good:
					cmd = opus_cmd(dests, bw, host, target_ip=target_ip)
				elif sm == "udp-flood" or ((sm is None or sm == "opus-voip") and not good):
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
						target_ip
					]
			else:
				cmd = []

			if len(cmd) > 0:
				env_new = os.environ.copy()
				env_new["RUST_BACKTRACE"] = "1"
				host_procs.append(host.popen(
					cmd, stdin=PIPE, stderr=sys.stdout,
					env=env_new
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
				for core_link in core_links:
					core_link.intf1.config(bw=ratio*float(capacity))
					core_link.intf2.config(bw=ratio*float(capacity))

		last_traffic_ratio = 0.0
		g_reward = 0.0
		reward = 0.0

		if ep > 0:
			#net.interact()
			pass

		learner_stats = [{} for _ in actors]
		learner_traces = [{} for _ in actors]
		learner_queues = [{"curr": ([], set(), set()), "future": set(), "pos": 0} for _ in actors]
		learner_fvecs = [{} for _ in actors]
		flows_to_query = []

		# Dict mapping flow-key to speed measurement and time at which it was taken.
		# [first_measures, current_measures]
		spiffy_measurements = [{}, {}]
		spiffy_verdict = {}

		for i in xrange(episode_length):
			# May need to early exit
			if interrupted[0]:
				break
			# Make the last actions a reality!
			if not spiffy_but_bad:
				enactActions(actors, learner_traces, vertex_map)
			else:
				curr_time = time.time()
				# NOTE: go over each entry of spiffy_measurements[0],
				# s_m[ip] = (rate, timestamp, unlimited, node)
				# if the entry in table 1 exists (and is older than spiffy_act_time)
				# look for the corresponding stats in table 2.
				# Use the ratio of current/first rate to determine a verdict
				# spiffy_verdict[ip] = true => bad (demote to complete filter)
				# then delete from the first two tables
				to_delete = []

				# ip_pair = (src_ip, dst_ip)
				inspect = False # TEMP
				for ip_pair in spiffy_measurements[0]:
					(src_ip, dst_ip) = ip_pair
					(rate, timestamp, unlimited, node) = spiffy_measurements[0][ip_pair]
					if not unlimited:
						unlimited = True
						#updateUpstreamRoute(node, ac_prob=0, target_ip=ip)
						# Note: I only have source ip here?
						isolateSpiffyFlow(spiffy_dest_switches, src_ip, dst_ip)

					if curr_time - timestamp >= spiffy_act_time and ip_pair in spiffy_measurements[1]:
						curr_rate = spiffy_measurements[1][ip_pair]
						# FIXME: needs to stack up against some notion of expected tbe. 
						tbe = float(curr_rate)/max(float(rate), 0.0001)
						bad_flow = tbe < spiffy_expansion_factor#1/(1-spiffy_drop_rate)
						spiffy_verdict[ip_pair] = bad_flow

						okaySpiffyFlow(spiffy_dest_switches, src_ip, dst_ip)
						if bad_flow:
							#updateUpstreamRoute(node, ac_prob=1, target_ip=ip)
							blockSpiffyFlow(spiffy_dest_switches, src_ip, dst_ip, ingress_switch=node)

						to_delete.append(ip_pair)
						print socket.inet_ntoa(struct.pack("I", src_ip)), rate, curr_rate, tbe, spiffy_expansion_factor, bad_flow, "should have been", (src_ip%2 == 1)
						#inspect = True
					else:
						spiffy_measurements[0][ip_pair] = (rate, timestamp, unlimited, node)

				if inspect:
					net.interact()

				for ip in to_delete:
					for el_i, el in enumerate(spiffy_measurements):
						if ip in el:
							del el[ip]

			if i == 1000:
				#net.interact()
				#quit()
				pass

			if randomise:
				counter = 0
				for (host, good, bw, link, ip, extern_no, sm) in all_hosts:
					curr_proc = host_procs[counter]
					finished = curr_proc.poll() is not None
					if good and finished:
						my_if = host.intf()
						if randomise_new_ip:
							link = my_if.link
							# get partner
							# unhook IF from both sides
							# create new between them with new IP (shazam!)
							# set hosts' default routes to new IF
							parent = (link.intf1 if my_if == link.intf2 else link.intf2).node
							newIP = genIP(good)
							switch_cmd(parent, [], ip_masker_message(newIP[0], ip), False)
							# TODO: think about changing bw/goodness?
							(lhs,) = struct.unpack("I", socket.inet_aton(newIP[0]))
							host_ip_mac_map[lhs] = host.MAC()

						if sm is None:
							cmd = th_cmd(dests, bw)
						elif sm == "opus-voip":
							cmd = opus_cmd(dests, bw, host)
						# restart traffic-host
						host_procs[counter] = host.popen(
							cmd, stdin=sys.stdout, stderr=sys.stderr
						)
					counter += 1

			presleep = time.time()

			# Wait, somehow
			time.sleep(dt)

			postsleep = time.time()

			#print postsleep - presleep
			preask = time.time()
			(time_ns, unfused_load_mbps, parsed_flows) = ask_stats(flows_to_query, len(monitored_links), len(learner_pos))
			postask = time.time()
			if print_times:
				print "total:", postask - preask

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
				if state_direction == "in":
					reward_src = unfused_total_mbps[2*n]
				elif state_direction == "out":
					reward_src = unfused_total_mbps[2*n + 1]
				return reward_src

			l_cap = (2.0 if state_direction == "fuse" else 1.0) * capacity

			first_sarsa = None

			flows_to_query = []

			datas = {}
			totals = {}
			g_rewards = {}
			g_reward = 0.0
			reward = 0.0

			dest_sum_data = [0.0, 0.0]
			direction_sum = [0.0, 0.0]
			for dest in dests:
				#use the data from all of:
				totals[dest] = 0.0
				datas[dest] = (0.0, 0.0)

				for link in dest_links[dest]:
					index = link_map[link]
					(data_g_o, data_b_o) = datas[dest]
					(data_g, data_b) = get_data(index)

					totals[dest] += get_total(index)
					datas[dest] = (data_g_o + data_g, data_b_o + data_b)
					dest_sum_data[0] += data_g
					dest_sum_data[1] += data_b

					unfused_start = index*2
					in_out = unfused_total_mbps[unfused_start:unfused_start+2]
					direction_sum[0] += in_out[0]
					direction_sum[1] += in_out[1]

				# assume that all dests are receiving an equal share of bw_all...
				r_g = safe_reward_func(std_marl, totals[dest], datas[dest][0], bw_all[0]/float(len(dests)),
					0.0, 0.0, 0.0, 0, l_cap, ratio)

				g_rewards[dest] = r_g

				# make the exported g_reward an average.
				g_reward += (r_g / float(len(dests)))

			#print g_reward, get_total(0), get_data(0)[0], bw_all[0], n_teams, l_cap, ratio

			# FIXME: make relevant to multi-dest.
			last_traffic_ratio = min(dest_sum_data[0]/bw_all[0], 1.0)
			if not (i % 10): print "\titer {}/{}, good:{}, load:{:.2f} ({:.2f},{:.2f})".format(i, episode_length, last_traffic_ratio, dest_sum_data[0] + dest_sum_data[1], *direction_sum)

			intime = time.time()
			for learner_no, (node_label, sarsa, leader_nodes) in enumerate(actors):
				node = vertex_map[node_label]


				if first_sarsa is None:
					first_sarsa = sarsa

				target_sarsa = first_sarsa if single_learner else sarsa

				def dumb_hash(*args):
					return 0

				def smart_hash(n_choices, src_ip, dst_ip, src_mac, *args):
					def bytify(mac):
						return mac.replace(":", "").decode("hex")
					src_mac_new = bytify(src_mac)
					dst_mac = bytify("00:00:00:01:00:00")
					vlan_id = 0 #u16
					ether_type = 0x800 #u16
					#src_ip is already a u32
					#dst_ip_new = socket.inet_pton(socket.AF_INET, dst_ip) # u32
					(lhs,) = struct.unpack("I", socket.inet_aton(dst_ip)) # u32
					port = 0 if submodel is not None else 80
					base = struct.pack(
						"<ssHHIIH",
						src_mac_new,
						dst_mac,
						vlan_id,
						ether_type,
						src_ip,
						lhs,
						port,
					)

					# winner selection according to Ben Pfaff
					# https://mail.openvswitch.org/pipermail/ovs-discuss/2018-March/046459.html
					# assume equal weight
					hashes = [hash(base + struct.pack("<I", i)) for i in xrange(n_choices)]
					winner = np.argmax(hashes)

					return winner

				# hash_fn = smart_hash if use_path_measurements else dumb_hash
				hash_fn = smart_hash if actions_target_flows else dumb_hash

				def indices_for_state_vec(dst_ip, src_ip, show_choices=False):
					curr = node_label
					end = dest_from_ip[dst_ip]
					path = [curr]
					while curr != end:
						next_set = list(dest_map[curr][end])
						if show_choices:
							print next_set
						curr = next_set[hash_fn(
							len(next_set),
							src_ip, dst_ip,
							host_ip_mac_map[src_ip] if src_ip in host_ip_mac_map else "00:00:00:00:00:00"
						)]
						path.append(curr)

					# have a complete path, convert now...
					path.reverse()
					parts = zip(path, path[1:])
					h0 = parts[0]
					h3 = parts[-1]
					internals = []
					if len(parts) == 1:
						internals = [h0, h3]
					else:
						usables = parts[1:-1]
						tert_pt = float(len(usables)) / 3.0
						internals.append(usables[int(tert_pt)])
						internals.append(usables[int(tert_pt*2)])

					return [h0] + internals + [h3]

				# here is where global state is built.
				# traditional "leader" is main_links[2]
				t_dest = dests[np.random.choice(len(dests))]
				main_links = indices_for_state_vec(t_dest[0][0], 0)

				state_vec = [total_mbps[link_map[x]] for x in main_links]

				l_rewards = {}
				# FIXME: reconcile multiple everything w/ marl's standard action...
				for dest in dests:
					# assume that all dests are receiving an equal share of bw_all...
					if use_path_measurements:
						r_l = g_rewards[dest]
					else:
						lead = leader_nodes if leader_nodes is not None else main_links[2]
						lead_i = link_map[lead]
						r_l = safe_reward_func(reward_func, totals[dest], datas[dest][0], bw_all[0]/float(len(dests)),
							get_total(lead_i), get_data(lead_i)[0], bw_teams[lead][0],
							n_teams, l_cap, ratio)

					l_rewards[dest] = r_l
					reward += r_l/float(len(dests)*len(actors))

				l_index = learner_no
				# if on hard mode, do some other stuff instead.
				if actions_target_flows:
					# props: (
					#  len_ns, sz_in, sz_out, [0-2]
					#  wnd_sz_in, wnd_sz_out, [3-4]
					#  pkt_in_sz_mean, pkt_in_sz_var, pkt_in_count, [5-7]
					#  pkt_out_sz_mean, pkt_out_sz_var, pkt_out_count, [8-10]
					#  wnd_iat_mean, wnd_iat_var [11-12]
					# )
					flow_space = learner_stats[l_index]
					flow_traces = learner_traces[l_index]
					flows_seen = parsed_flows[l_index]
					queue_holder = learner_queues[l_index]
					fvec_holder = learner_fvecs[l_index]

					#if i%10 == 0:
					#	print "laerner {} occupying:".format(l_index), len(flow_space), len(flow_traces), len(flows_to_query)

					total_spent = 0.0
					def can_act():
						return trs_maxtime is None or total_spent <= trs_maxtime

					# learner_queues = [{"curr": ([], set(), set()), "future": set(), "pos": 0} for _ in learner_pos]

					(local_work, local_work_set, local_visited_set) = queue_holder["curr"]
					local_pos = queue_holder["pos"]
					#print "true", state_vec

					# TODO: strip old entries?
					# PROCESS ALL NEW DATA.
					for (src_ip, props_dict) in flows_seen:
						for (dst_ip, props) in props_dict.iteritems():
							# we know src, and dst. rebuild state-vec.
							main_links = indices_for_state_vec(dst_ip, src_ip)

							state_vec = [total_mbps[link_map[x]] for x in main_links]
							#print state_vec

							flows_to_query.append(src_ip)

							ip_pair = (src_ip, dst_ip)

							if ip_pair not in flow_space:
								flow_space[ip_pair] = {
									"ip": src_ip,
									"last_act": 0.0 if not spiffy_mode else 0.05,
									"last_rate_in": -1.0,
									"last_rate_out": -1.0,
									"pkt_in_count": 0,
									"pkt_out_count": 0,
								}
							l = flow_space[ip_pair]

							l["cx_ratio"] = min(*props[1:3]) / max(*props[1:3])
							l["length"] = props[0]
							l["size"] = props[1] + props[2]
							l["mean_iat"] = props[11]
							l["pkt_in_count"] += props[7]
							l["pkt_out_count"] += props[10]
							l["pkt_in_wnd_count"] = props[7]
							l["pkt_out_wnd_count"] = props[10]
							l["mean_bpp_in"] = props[5]
							l["mean_bpp_out"] = props[8]
							l["bytes_in"] = props[3]
							l["bytes_out"] = props[4]

							observed_rate_in = mbpsify(props[3])
							observed_rate_out = mbpsify(props[4])

							if l["last_rate_in"] < 0.0:
								l["last_rate_in"] = observed_rate_in
								l["last_rate_out"] = observed_rate_out
							l["delta_in"] = observed_rate_in - l["last_rate_in"]
							l["delta_out"] = observed_rate_out - l["last_rate_out"]
							total_vec = state_vec + flow_to_state_vec(l)
							flow_space[ip_pair] = l

							fvec = combine_flow_vecs(fvec_holder[ip_pair], total_vec) if ip_pair in fvec_holder else total_vec
							fvec_holder[ip_pair] = fvec
							# maybe push this seen IP into the future set
							# When? If it's not in the current work set,
							# or it has been visited and is in the current set.
							if ip_pair not in local_work_set or ip_pair in local_visited_set:
								queue_holder["future"].add(ip_pair)

							if spiffy_but_bad:
								# if already under scrutiny or if there's enough space to add, then (maybe) act
								# also, don't act if we already made a verdict...
								total_s_bw = observed_rate_in #+ observed_rate_out
								if spiffy_traffic_dir == "out":
									total_s_bw = observed_rate_out
								elif spiffy_traffic_dir == "inout":
									total_s_bw += observed_rate_out
								#print "spiffy says", ip_pair, "is pushing", (observed_rate_in, observed_rate_out), total_s_bw

								# don't apply this to flows under a certain traffic rate? Pick a sensible threshold
								if spiffy_mbps_cutoff is not None and total_s_bw < spiffy_mbps_cutoff and total_s_bw > 0.0:
									#pass
									spiffy_verdict[ip_pair] = False
									#print "spiffy pardoned flow [small]", ip_pair

								expt_count = max(spiffy_min_experiments, min(spiffy_max_experiments, int(spiffy_pick_prob * float(len(flows_seen)))))
								#print "aiming to run:", expt_count, "have:", len(spiffy_measurements[0])

								# FIXME: make this limit apply per-destination...
								if ip_pair in spiffy_measurements[0]:
									spiffy_measurements[1][ip_pair] = total_s_bw
								elif ip_pair not in spiffy_verdict and total_s_bw > 0.0 and len(spiffy_measurements[0]) < expt_count and np.random.random() < spiffy_pick_prob:
									print "spiffy observing flow", ip_pair
									spiffy_measurements[0][ip_pair] = (total_s_bw, time.time(), False, node)

					# FIXME: ensure that all the code if prepared to take ip_pair, NOT ip.
					if local_pos >= len(local_work):
						local_pos = 0
						local_work_set = queue_holder["future"]
						local_visited_set = set()
						queue_holder["future"] = set()
						# take a shuffle! Ideally without perturbing RNG
						# used for IP generation...
						# I'd fix that, but the amount of new IPs
						# we need is stochastic anyhow.
						local_work = list(local_work_set)
						random.shuffle(local_work)
					else:
						#print "existing work: task size {}, pos {}".format(len(local_work_set), local_pos)
						pass

					flows_procd = 0
					# ACT ON A SUBSET OF CURRENT
					while can_act() and local_pos < len(local_work):
						ip_pair = local_work[local_pos]
						local_visited_set.add(ip_pair)

						s_t = time.time()
						l = flow_space[ip_pair]

						# Each needs its own view of the state...
						# (and specifies its restriction thereof)
						# Combine these to get a vector of likelihoods,
						# get the highest-epsilon to calculate the action.
						# Then update each model with the TRUE action chosen.
						fvec = fvec_holder[ip_pair]
						total_vec = fvec[:feature_max]

						# single_learner support: just take firstmost...
						# structure is historical; scan across lengthwise...
						s_tree_t = 0
						s_tree_l = 0
						if not single_learner and len(contributors) > 0:
							(s, r) = contributors[0]
							branch_len = len(s[0])
							s_tree_t = learner_no / branch_len
							s_tree_l = learner_no % branch_len
						subactors = [(target_sarsa, restrict)] + [(s_tree[s_tree_t][s_tree_l], r) for (s_tree, r) in contributors]

						last_sarsa = sarsa
						ac_vals = np.zeros(len(sarsa.actions))
						substates = []
						need_decay = True

						for s_ac_num, (s, r) in enumerate(subactors):
							tx_vec = total_vec if r is None else [total_vec[i] for i in r]
							state = s.to_state(np.array(tx_vec))
							#print "state len (from, to)", (len(tx_vec), len(state))

							# if there was an earlier decision made on this flow, then update the past state estimates associated.
							# Compute and store the intended update for each flow.
							if ip_pair in flow_traces:
								dm = [i] if record_deltas_in_times else None

								dat = flow_traces[ip_pair]
								(st, z, narrowing_in_use) = dat[0][s_ac_num]
								machine = dat[2]

								# handful of steps:
								#  only draw new if none
								#  decrement uses
								#  don't use in update step if just generated
								#  don't use in action step if about to expire
								allow_update_narrowing = False
								allow_action_narrowing = False

								# narrowing removal---opens up flow for other state exam again
								if narrowing_in_use is not None and narrowing_in_use[0] <= 0:
									narrowing_in_use = None

								if narrowing_in_use is None and (np.random.uniform() < s.get_epsilon() * explore_feature_isolation_modifier):
									# remaining updates, narrowing itself.

									# If always global, play about with the selection (raise LB).
									mod = 1 if always_include_global else 0
									narrowing_in_use = [
										explore_feature_isolation_duration,
										([0] if always_include_global else []) + [np.random.choice(s.tiling_set_count-mod)+mod],
									]
									allow_action_narrowing = True
								elif narrowing_in_use is not None:
									narrowing_in_use[0] -= 1
									allow_update_narrowing = True
									allow_action_narrowing = narrowing_in_use[0] > 0

								(would_choose, new_vals, z_vec) = s.update(
									state,
									l_rewards[dest_from_ip[ip_pair[1]]],
									(st, dat[1], z),
									decay=False,
									delta_space=dm,
									action_narrowing=None if not allow_action_narrowing else narrowing_in_use[1],
									update_narrowing=None if not allow_update_narrowing else narrowing_in_use[1],
								)

								if record_deltas_in_times:
									action_comps[-1].append(dm)
							else:
								(would_choose, new_vals, z_vec) = s.bootstrap(state)
								need_decay = False
								machine = AcTrans()
								narrowing_in_use = None

							ac_vals += new_vals
							substates.append((state, z_vec, narrowing_in_use))

							last_sarsa = s

						l_action = last_sarsa.select_action_from_vals(ac_vals)
						machine.move(l_action)
						flow_traces[ip_pair] = (substates, l_action, machine, z_vec, [True])

						if need_decay:
							for (s, _) in subactors:
								s.decay()

						observed_rate_in = l["last_rate_in"] + l["delta_in"]
						observed_rate_out = l["last_rate_out"] + l["delta_out"]

						# TODO: maybe only update this whole thing if we're choosing to examine this flow.
						l["last_act"] = machine.action()#l_action
						l["last_rate_in"] = observed_rate_in
						l["last_rate_out"] = observed_rate_out

						flow_space[ip] = l
						# print l
						# End time.
						e_t = time.time()
						total_spent += e_t - s_t

						if record_times:
							action_comps[-1].append((i, e_t - s_t))

						learner_traces[l_index] = flow_traces
						local_pos += 1
						flows_procd += 1
						del fvec_holder[ip_pair]

					#print "Managed: {}/{}-{} flows in under {}".format(flows_procd, local_pos-flows_procd, len(local_work_set), trs_maxtime)

					queue_holder["curr"] = (local_work, local_work_set, local_visited_set)
					queue_holder["pos"] = local_pos
				else:
					prev_state = learner_traces[l_index]
					if prev_state == {}:
						machine = AcTrans()
						prev_state = (sarsa.last_act, machine)

					(last_act, machine) = prev_state

					# Start time of action computation
					s_t = time.time()

					# Encode state (as seen by this learner)
					state = sarsa.to_state(np.array(state_vec))

					# Learn!
					target_sarsa.update(state, reward, last_act)
					machine.move(sarsa.last_act[1])
					learner_traces[l_index] = (sarsa.last_act, machine)

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

		for server_proc in server_procs:
			try:
				server_proc.terminate()
			except:
				print "couldn't cleanly shutdown server process..."
		if ctl_proc is not None:
			#print "I have good reason to believe that I'm killing ryu."
			try:
				ctl_proc.terminate()
			except:
				print "couldn't cleanly shutdown control process..."
		for proc in host_procs:
			try:
				proc.terminate()
			except:
				print "couldn't cleanly shutdown host process..."

		host_procs = []
		server_procs = []
		ctl_proc = None

		net.stop()

		store_sarsas = team_sarsas
		next_ip = [1]

		#for sar in store_sarsas:
			#print sar[0].values
			#pass

	# Okay, done!
	# Run interesting stats stuff here? Just save the results? SAVE THE LEARNED MODEL?!
	return (rewards, good_traffic_percents, total_loads, store_sarsas, random.getstate(), action_comps)
