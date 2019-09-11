from contextlib import closing
#import cPickle as pickle
import pickle
import socket
import struct

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_4
from ryu.lib.packet import packet, ipv4, ethernet, arp, ether_types, in_proto

ipv4_eth = 0x0800

# as commanded by the dark lord
controller_build_port = 6666

def full_dpid(incomplete_id):
	return "{:016x}".format(incomplete_id)

class SmartishRouter(app_manager.RyuApp):
	OFP_VERSIONS = [ofproto_v1_4.OFP_VERSION]

	# ctor
	def __init__(self, *args, **kwargs):
		super(SmartishRouter, self).__init__(*args, **kwargs)
		#print "I am large, and in charge"
		self.subnet = "10.0.0.0"
		self.netmask = "255.255.255.0"
		# may want to use the actual outbound mac, later
		self.pretend_mac = "00:00:00:01:00:00"
		self.outsiders = {}
		self.ignores = {}

		# probably open a conn to mininet here, and wait to receive params...
		with closing(
			socket.create_connection(("127.0.0.1", controller_build_port))
		) as data_sock:
			# read a length (usize, 8bytes) then that many bytes in turn.
			# unpickle to receive the data needed to start controlling.

			buf = b""
			while len(buf) < 8:
				buf += data_sock.recv(4096)
			(pickle_len,) = struct.unpack("!Q", buf[:8])

			buf = buf[8:]
			while len(buf) < pickle_len:
				buf += data_sock.recv(4096)

			(routes, ways_out, macs, not_clever, ecmp_routes) = pickle.loads(buf)
			print(pickle_len)
			print(routes, macs)
			print(ways_out)
			print(ecmp_routes)
			self.entry_map = routes
			self.escape_map = ways_out
			self.macs = macs
			self.no_record_escape = not_clever
			self.ecmp_routes = ecmp_routes
		#print "I am now alive, controlling all...!"

	def local_ip(self):
	   return (self.subnet, self.netmask)

	# initialisation, post-handshake.
	@set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
	def switch_features_handler(self, ev):
		msg = ev.msg
		datapath = msg.datapath
		n_tables = msg.n_tables

		ofp = datapath.ofproto
		parser = datapath.ofproto_parser

		self.logger.debug("Seeing %d tables on dp 0x%016x:"
			"need 4", n_tables, msg.datapath_id)

		local = self.local_ip()
		dpid = full_dpid(datapath.id)

		if dpid not in self.entry_map:
			#print "I believe", dpid, "to be external (?)"
			# this is an external switch, it's being managed elsewhere...
			return

		self.ignores[dpid] = set()

		# Table 0: (categorisation)
		#	arp -> proxy
		#	local src, local dest -> T3
		#	local dest -> T1
		#	local src -> T2

		t = 0
		self.add_flow(datapath, 1,
			parser.OFPMatch(
				eth_type=ether_types.ETH_TYPE_ARP,
			),
			actions=[parser.OFPActionOutput(ofp.OFPP_CONTROLLER)],
			table_id=t)
		self.add_flow(datapath, 1,
			parser.OFPMatch(
				eth_type=ipv4_eth,
				ipv4_src=local,
				ipv4_dst=local,
			),
			next_table=3,
			table_id=t)
		self.add_flow(datapath, 1,
			parser.OFPMatch(
				eth_type=ipv4_eth,
				ipv4_dst=local,
			),
			next_table=1,
			table_id=t)
		self.add_flow(datapath, 1,
			parser.OFPMatch(
				eth_type=ipv4_eth,
				ipv4_src=local,
			),
			next_table=2,
			table_id=t)


		# Table 1: (register external dests)
		#	((src ip -> T3))
		#	miss -> controller

		t = 1
		if self.no_record_escape == "always":
			self.table_miss(datapath,
				next_table=3,
				table_id=t)
		else:
			self.table_miss(datapath,
				actions=[parser.OFPActionOutput(ofp.OFPP_CONTROLLER)],
				table_id=t)
		# if we don't record waybacks for UDP, just forward them to the dst table (hi-prio)
		if self.no_record_escape == "udp":
			self.add_flow(datapath, 2,
				parser.OFPMatch(
					eth_type=ipv4_eth,
					ip_proto=in_proto.IPPROTO_UDP,
				),
				next_table=3,
				table_id=t)

		# Table 2: (external dest routing)
		#	((dest ip -> output route))
		#	miss -> flood

		t = 2
		# Set up a group according to ways out.
		# Mode: select (i.e. ECMP hashed)
		# Each bucket corresponds to an identified "way out".
		# On miss, use this group action.
		# For this network, only one "outside" so only one group, 0.
		g = 0
		self.add_port_split(datapath, list(self.escape_map[dpid]), group_id=g)

		self.table_miss(datapath,
			# actions=[parser.OFPActionOutput(ofp.OFPP_FLOOD)],
			actions=[parser.OFPActionGroup(g)],
			table_id=t)

		# Table 3: (internal dest routing)
		#	dest ip -> output pre-solved

		t = 3

		if dpid not in self.ecmp_routes:
			print("Switch {} does not appear in the routing directory---no paths use it. Try upping the host count?".format(dpid))
			return

		g_dict = self.ecmp_routes[dpid]
		for ip, ports in g_dict.items():
			g += 1
			ps = []
			p_actions = []
			for port, adjacent in ports:
				ps.append(port)
				p_actions.append([] if not adjacent else [
					parser.OFPActionSetField(
						eth_dst=self.macs[ip],
					),
					parser.OFPActionSetField(
						eth_src=self.pretend_mac,
					),
				])

			self.add_port_split(datapath,
				ps,
				bucket_prepend_actions=p_actions,
				group_id=g,
			)

			self.add_flow(datapath, 1,
				parser.OFPMatch(
					eth_type=ipv4_eth,
					ipv4_dst=(ip, "255.255.255.255"),
				),
				# actions=rewrites+[parser.OFPActionOutput(port)],
				actions=[parser.OFPActionGroup(g)],
				table_id=t
			)

		print("done setting up switch")
			
	def add_group(self, datapath, buckets=[], command=None, type_=None, group_id=0):
		ofproto = datapath.ofproto
		parser = datapath.ofproto_parser

		if command is None:
			command = ofproto.OFPGC_ADD
		if type_ is None:
			type_ = ofproto.OFPGT_SELECT

		mod = parser.OFPGroupMod(datapath, command,
			type_, group_id, buckets)

		datapath.send_msg(mod)

	def add_port_split(self, datapath, ports, port_weights=None, bucket_prepend_actions=None, **kwargs):
		ofproto = datapath.ofproto
		parser = datapath.ofproto_parser
		# THis SHOULD pass through group_id...
		if port_weights is None:
			port_weights = [1 for e in ports]

		if bucket_prepend_actions is None:
			bucket_prepend_actions = [[] for e in ports]

		buckets = []
		for (port, weight, prepend) in zip(ports, port_weights, bucket_prepend_actions):
			bucket = parser.OFPBucket(weight, actions=prepend + [
				parser.OFPActionOutput(port)
			])
			buckets.append(bucket)

		self.add_group(datapath, buckets, **kwargs)

	def add_flow(self, datapath, priority, match, actions=None, table_id=0, next_table=None, importance=1):
		ofproto = datapath.ofproto
		parser = datapath.ofproto_parser

		# construct flow_mod message and send it.
		inst = []
		if actions is not None:
			inst.append(
				parser.OFPInstructionActions(
					ofproto.OFPIT_APPLY_ACTIONS,
					actions
				)
			)
		if next_table is not None:
			inst.append(
				parser.OFPInstructionGotoTable(next_table),
			)
		mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
			match=match, instructions=inst, table_id=table_id,
			importance=importance)

		datapath.send_msg(mod)

	def table_miss(self, datapath, *args, **kwargs):
		self.add_flow(datapath, 0, None, *args, **kwargs)

	def arp_reply(self, in_arp):
		e = ethernet.ethernet(
			dst=in_arp.src_mac, src=self.pretend_mac,
			ethertype=ether_types.ETH_TYPE_ARP,
		)
		a = arp.arp(
			opcode=arp.ARP_REPLY,
			src_ip=in_arp.dst_ip,
			src_mac=self.pretend_mac,
			dst_ip=in_arp.src_ip,
			dst_mac=in_arp.src_mac
		)

		p = packet.Packet()
		p.add_protocol(e)
		p.add_protocol(a)
		p.serialize()

		return p

	# handling of unseen flow entries/packet-ins
	@set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
	def packet_in_handler(self, ev):
		#print "been upcalled!"
		msg = ev.msg
		dp = msg.datapath
		ofp = dp.ofproto
		ofp_parser = dp.ofproto_parser
		dpid = full_dpid(dp.id)

		in_port = msg.match["in_port"]

		#print "by", dpid

		# okay: is this an ARP or IPv4 packet?
		# if ARP request, we want to send a reply masquerading as the dest
		# (with dest set to out_port)
		# if IPv4, register the flow.

		pkt = packet.Packet(msg.data)
		arp_pkt = pkt.get_protocol(arp.arp)
		ipv4_pkt = pkt.get_protocol(ipv4.ipv4)
		ether_pkt = pkt.get_protocol(ethernet.ethernet)

		if dpid not in self.ignores:
			self.ignores[dpid] = set()

		ignore_list = self.ignores[dpid]

		if arp_pkt is not None:
			#print "it's ARP"
			# in both cases: build and send a reply
			reply = self.arp_reply(arp_pkt)
			#print "reply built"

			#print "action built"
			#print reply, in_port, reply.data
			out = ofp_parser.OFPPacketOut(
				datapath=dp, buffer_id=0xffffffff,
				in_port=ofp.OFPP_CONTROLLER,
				actions=[ofp_parser.OFPActionOutput(in_port)],
				data=reply.data,
			)
			dp.send_msg(out)

			#print "reply sent"

			if dpid not in self.entry_map:
				# external: install fast route home + rewrite
				#print "fast return..."
				actions = [
					ofp_parser.OFPActionSetField(
						eth_dst=arp_pkt.src_mac,
					),
					ofp_parser.OFPActionSetField(
						eth_src=self.pretend_mac,
					),
					ofp_parser.OFPActionOutput(in_port)
				]
				#print "built actions"
				self.add_flow(dp, 1,
					ofp_parser.OFPMatch(
						eth_type=ipv4_eth,
						ipv4_dst=(arp_pkt.src_ip, "255.255.255.255"),
					),
					actions=actions,
					table_id=1,
				)
				#print "route home installed for external"

				self.outsiders[arp_pkt.src_mac] = arp_pkt.src_ip

			return
		elif dpid not in self.entry_map:
			self.logger.debug("non-arp upcall from external")

			if ether_pkt.src not in self.outsiders:
				return

			true_ip = self.outsiders[ether_pkt.src]
			self.logger.debug("Found it in outsiders")
			self.logger.debug("src:{}, dst:{}".format(ipv4_pkt.src, ipv4_pkt.dst))
			self.logger.debug("true_src:{}".format(true_ip))

			# Do the logic for IP rewrite installation here...
			# 1. Cancel the CONTROLLER rule in table 0.
			# Replace SRC, then send on output 1...
			actions = [
				ofp_parser.OFPActionSetField(
					ipv4_src=ipv4_pkt.src,
				),
				ofp_parser.OFPActionOutput(1)
			]
			self.add_flow(dp, 1,
				ofp_parser.OFPMatch(
					eth_type=ipv4_eth,
					ipv4_src=(true_ip, "255.255.255.255")
				),
				actions=actions,
			)

			# 2. Update the MAC-rewrite to also rewrite dstIP if new IP seen.
			actions = [
				ofp_parser.OFPActionSetField(
					eth_dst=ether_pkt.src,
				),
				ofp_parser.OFPActionSetField(
					eth_src=self.pretend_mac,
				),
				ofp_parser.OFPActionSetField(
					ipv4_dst=true_ip,
				),
				ofp_parser.OFPActionOutput(in_port)
			]

			self.add_flow(dp, 1,
				ofp_parser.OFPMatch(
					eth_type=ipv4_eth,
					ipv4_dst=(ipv4_pkt.src, "255.255.255.255"),
				),
				actions=actions,
				table_id=1,
			)
			# 3. Hand back to switch.
			actions = [ofp_parser.OFPActionOutput(ofp.OFPP_TABLE)]
			out = ofp_parser.OFPPacketOut(
				datapath=dp, buffer_id=msg.buffer_id, in_port=in_port,
				actions=actions, data=msg.data)
			#print out, dp, msg.buffer_id, in_port, actions, msg.data.encode("hex_codec"), port, adj
			dp.send_msg(out)
			self.logger.debug("handed back")
			return

		#print "it's ipv4?"
		#if ipv4_pkt.src in ignore_list:
		#	return
		#ignore_list.add(ipv4_pkt.src)

		external_ip = ipv4_pkt.src

		#print ipv4_pkt

		# Packet in means we've been notified about a flow (out->in)
		# which has yet to be seen. Record that we've seen it in T2
		# (and forward from T1->T3), and add a flow rule in T2 matching
		# the external destination to the in-port we saw here.
		#
		# NOTE: could have this pre-emptively submit flow rules to the 
		# other nodes up the chain, but that might be non-trivial...

		# src recognised
		self.add_flow(dp, 1,
			ofp_parser.OFPMatch(
				eth_type=ipv4_eth,
				ipv4_src=external_ip,
			),
			next_table=3,
			table_id=1,
			importance=0)

		# way out being registered for this ip.
		self.add_flow(dp, 1,
			ofp_parser.OFPMatch(
				eth_type=ipv4_eth,
				ipv4_dst=external_ip,
			),
			[ofp_parser.OFPActionOutput(in_port)],
			table_id=2,
			importance=0)
			
		#print ipv4_pkt.src, ipv4_pkt.dst
		(port, adj) = (1, True) \
			if dpid not in self.entry_map \
			else self.entry_map[dpid][ipv4_pkt.dst]

		#rewrites = [] if not adj else [
		#	ofp_parser.OFPActionSetField(eth_dst=self.macs[ipv4_pkt.dst])
		#]

		# Don't try and guess where this is to go, let the switch deal with it,
		# since it's pre-primed with knowledge of internal routes...
		# note: goto-table is an instr, not action...
		#actions=rewrites + [ofp_parser.OFPActionOutput(port)]
		actions = [ofp_parser.OFPActionOutput(ofp.OFPP_TABLE)]
		out = ofp_parser.OFPPacketOut(
			datapath=dp, buffer_id=msg.buffer_id, in_port=in_port,
			actions=actions, data=msg.data)
		#print out, dp, msg.buffer_id, in_port, actions, msg.data.encode("hex_codec"), port, adj
		dp.send_msg(out)

