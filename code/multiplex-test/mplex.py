from mininet.topo import Topo
from mininet.node import OVSSwitch, RemoteController
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.net import Mininet
from mininet.clean import Cleanup

import twink.ofp5 as ofp
import twink.ofp5.build as ofpb
import twink.ofp5.oxm as ofpm
import twink.ofp5.parse as ofpp

import csv
import itertools
import json
import numpy as np
import os
import random
import signal
import socket
from subprocess import PIPE, Popen
import sys
import time

def mplexExperiment(
		n = 5,
		inc_function = None,

		udp = False,

		pdrop_min = 0.0,
		pdrop_max = 1.0,
		pdrop_stride = 0.1,

		playback_file = "../../data/pcaps/bigFlows.pcap",
		playback = False,

		linkopts = {},
		base_iperf_port = 5201,

		csv_dir = None,
	):

	if inc_function is None:
		inc_function = lambda last, i, n: float(i+1)

	# helpers

	initd_host_count = [0]
	initd_switch_count = [0]
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
		if not False:#switch.listenPort:
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

	# Downstream should be computed similarly, but without the probdrops or anything like that.
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

	def updateUpstreamRoute(switch, out_port=1, ac_prob=0.0, ip="10.0.0.1"):
		# Turn from prob_drop into prob_send!
		prob = 1 - ac_prob
		p_drop_num = pdrop(prob)
		#p_drop = "" if ac_prob == 0.0 else "probdrop:{},".format(p_drop_num)
		p_drop = "probdrop:{},".format(p_drop_num)

		cmd_tail = [
			"in_port=*,ip,nw_dst={},actions={}\"{}-eth{}\"".format(ip, p_drop, switch.name, out_port)
		]

		# Try building that message from scratch, here.
		#msg = flow_pdrop_msg[:-20] + ofpb._pack("I", p_drop_num) + flow_pdrop_msg[-16:]


		msg = ofpb.ofp_flow_mod(
			None, 0, 0, 0, ofp.OFPFC_ADD,
			0, 0, 1, None, None, None, 0, 1,
			ofpb.ofp_match(ofp.OFPMT_OXM, None, [
				# Need to match Dest IP against curr host's.
				ofpm.build(None, ofp.OFPXMT_OFB_ETH_TYPE, False, 0, 0x0800, None),
				ofpm.build(None, ofp.OFPXMT_OFB_IPV4_DST, False, 0, socket.inet_aton(ip), None)
			]),
			ofpb.ofp_instruction_actions(ofp.OFPIT_WRITE_ACTIONS, None, [
				# Looks like 29 is the number I picked for Pdrop.
				ofpb._pack("HHI", 29, 8, p_drop_num),
				ofpb.ofp_action_output(None, 16, out_port, 65535)
			])
		)

		switchRouteCommand(switch, cmd_tail, msg)

	def updateDownstreamRoute(switch, host, out_port):
		ip = host.IP()

		cmd_tail = [
			"in_port=*,ip,nw_dst={},actions=\"{}-eth{}\"".format(ip,switch.name, out_port)
		]

		msg = ofpb.ofp_flow_mod(
			None, 0, 0, 0, ofp.OFPFC_ADD,
			0, 0, 1, None, None, None, 0, 1,
			ofpb.ofp_match(ofp.OFPMT_OXM, None, [
				# Need to match Dest IP against curr host's.
				ofpm.build(None, ofp.OFPXMT_OFB_ETH_TYPE, False, 0, 0x0800, None),
				ofpm.build(None, ofp.OFPXMT_OFB_IPV4_DST, False, 0, socket.inet_aton(ip), None)
			]),
			ofpb.ofp_instruction_actions(ofp.OFPIT_WRITE_ACTIONS, None, [
				# Looks like 29 is the number I picked for Pdrop.
				ofpb.ofp_action_output(None, 16, out_port, 65535)
			])
		)

		switchRouteCommand(switch, cmd_tail, msg)

	def floodRoute(switch):
		cmd_tail = [
			"actions=flood"
		]

		msg = ofpb.ofp_flow_mod(
			None, 0, 0, 0, ofp.OFPFC_ADD,
			0, 0, 1, None, None, None, 0, 1,
			ofpb.ofp_match(None, None, None),
			ofpb.ofp_instruction_actions(ofp.OFPIT_WRITE_ACTIONS, None, [
				# Looks like 29 is the number I picked for Pdrop.
				ofpb.ofp_action_output(None, 16, ofp.OFPP_FLOOD, 65535)
			])
		)

		switchRouteCommand(switch, cmd_tail, msg)

	def switchRouteCommand(switch, cmd_tail, msg):
		name = switch.name

		if not switch.listenPort:
			listenAddr = "unix:/tmp/{}.listen".format(switch.name)
		else:
			listenAddr = "tcp:127.0.0.1:{}".format(switch.listenPort)

		cmd_list = [
			"ovs-ofctl",
			"add-flow",
			listenAddr
		] + cmd_tail
		
		if alive:
			updateOneRoute(switch, cmd_list, msg)
		else:
			route_commands[0].append((switch, cmd_list, msg))

	def enactActions(learners, sarsas):
		for (node, sarsa) in zip(learners, sarsas):
			(_, action, _) = sarsa.last_act
			updateUpstreamRoute(node, ac_prob=action)

	def buildNet(n_hosts):
		server = newNamedHost()
		server_switch = newNamedSwitch()

		core_link = trackedLink(server, server_switch)
		assignIP(server)

		hosts = []
		last_bw = 0.0

		for i in xrange(n_hosts):
			h = newNamedHost()
			bw = inc_function(last_bw, i, n_hosts)
			last_bw = bw

			trackedLink(server_switch, h)

			hosts.append((h, bw))
			assignIP(h)

			updateDownstreamRoute(server_switch, h, i+2)

		updateUpstreamRoute(server_switch)

		floodRoute(server_switch)

		return (server, core_link, server_switch, hosts)

	def pdrop(prob):
		return int(prob * 0xffffffff)

	def fxrange(start, stop, step):
		curr = start
		while curr <= stop:
			yield curr
			curr += step

	### THE EXPERIMENT? ###

	net = Mininet(link=TCLink)
	alive = False

	Cleanup.cleanup()

	(server, core_link, server_switch, hosts) = buildNet(n)

	net.start()
	alive = True
	executeRouteQueue()

	print "starting procs"
	server_procs = [server.popen(["iperf3", "-s", "-p", str(base_iperf_port+x)], stdin=PIPE, stderr=sys.stderr) for x in xrange(n)]
	host_procs = [host.popen(
		["iperf3",
		"-c", server.IP(),
		"-i", str(0.5),
		"-p", str(base_iperf_port+i),
		"-b", "{}M".format(bw),
		"-t", str(32),
		"-J"] +
		(["-u"] if udp else []), 
		stdin=PIPE, stdout=PIPE, stderr=sys.stderr) for i, (host, bw) in enumerate(hosts)
	]

	#net.interact()

	time.sleep(0.5)

	for step in xrange(20):
		updateUpstreamRoute(server_switch, ac_prob=step/20.0)
		print "pushing drop rate", step/20.0, "at t =",0.5+1.5*(step)
		time.sleep(1.5)

	print "gathering stats..."
	updateUpstreamRoute(server_switch, ac_prob=0.0)
	datas_pre = [proc.communicate() for proc in host_procs]
	datas = [json.loads(data[0]) for data in datas_pre]
	print "gathered"

	if csv_dir is not None:
		with open(csv_dir, 'w') as csv_file:
			out = csv.writer(csv_file)
			for (_, bw), data in zip(hosts, datas):
				for inter in data["intervals"]:
					inner = inter["sum"]
					out.writerow([bw, inner["end"], float(inner["bits_per_second"])/1e6])
					if udp: print "bw=", bw, "lost", data["end"]["sum"]["lost_percent"]

	print "output written, cleaning up..."

	removeAllSockets()

	for proc in host_procs + server_procs:
		try:
			proc.terminate()
		except:
			pass

	net.stop()

	return None

mplexExperiment(n=5, csv_dir="../../results/mplex-tcp.csv")
mplexExperiment(n=5, udp=True, csv_dir="../../results/mplex-udp.csv")
