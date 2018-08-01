from contextlib import closing
import cPickle as pickle
import socket
import struct

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_4
from ryu.lib.packet import packet
from ryu.lib.packet import ipv4

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
		self.subnet = "10.0.0.0"
		self.netmask = "255.255.255.0"

		# probably open a conn to mininet here, and wait to receive params...
		with closing(
			socket.create_connection(("127.0.0.1", controller_build_port))
		) as data_sock:
			# read a length (usize, 8bytes) then that many bytes in turn.
			# unpickle to receive the data needed to start controlling.

			buf = ""
			while len(buf) < 8:
				buf += data_sock.recv(4096)
			(pickle_len,) = struct.unpack("!Q", buf[:8])

			buf = buf[8:]
			while len(buf) < pickle_len:
				buf += data_sock.recv(4096)
			self.entry_map = pickle.loads(buf)

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

		print "made friends with", hex(datapath.id), ", telling them what to do..."
		print "address was...", datapath.address

		self.logger.debug("Seeing %d tables on dp 0x%016x:"
			"need 4", n_tables, msg.datapath_id)

		local = self.local_ip()

		# Table 0: (categorisation)
		#	local src, local dest -> T3
		#	local dest -> T1
		#	local src -> T2

		t = 0
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
		self.table_miss(datapath,
			actions=[parser.OFPActionOutput(ofp.OFPP_CONTROLLER)],
			table_id=t)

		# Table 2: (external dest routing)
		#	((dest ip -> output route))
		#	miss -> flood

		t = 2
		self.table_miss(datapath,
			actions=[parser.OFPActionOutput(ofp.OFPP_FLOOD)],
			table_id=t)

		# Table 3: (internal dest routing)
		#	dest ip -> output pre-solved

		t = 3

		dpid = full_dpid(datapath.id)

		if dpid in self.entry_map:
			l_dict = self.entry_map[dpid]
			for ip, port in l_dict.iteritems():
				self.add_flow(datapath, 1,
					parser.OFPMatch(
						eth_type=ipv4_eth,
						ipv4_dst=(ip, "255.255.255.255"),
					),
					actions=[parser.OFPActionOutput(port)],
					table_id=t
				)
		else:
			self.add_flow(datapath, 1,
				parser.OFPMatch(
					eth_type=ipv4_eth,
					ipv4_dst=("10.0.0.1", "255.255.255.255"),
				),
				actions=[parser.OFPActionOutput(0)],
				table_id=t
			)
			
	def add_flow(self, datapath, priority, match, actions=None, table_id=0, next_table=None):
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
			match=match, instructions=inst, table_id=table_id)

		datapath.send_msg(mod)

	def table_miss(self, datapath, *args, **kwargs):
		self.add_flow(datapath, 0, None, *args, **kwargs)

	# handling of unseen flow entries/packet-ins
	@set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
	def packet_in_handler(self, ev):
		msg = ev.msg
		dp = msg.datapath
		ofp = dp.ofproto
		ofp_parser = dp.ofproto_parser

		pkt = packet.Packet(msg.data)
		ipv4_pkt = pkt.get_protocol(ipv4.ipv4)
		external_ip = ipv4_pkt.src

		# Packet in means we've been notified about a flow (out->in)
		# which has yet to be seen. Record that we've seen it in T2
		# (and forward from T1->T3), and add a flow rule in T2 matching
		# the external destination to the in-port we saw here.
		#
		# NOTE: could have this pre-emptively submit flow rules to the 
		# other nodes up the chain, but that might be non-trivial...

		# src recognised
		self.add_flow(datapath, 1,
			parser.OFPMatch(
				eth_type=ipv4_eth,
				ipv4_src=external_ip,
			),
			next_table=3,
			table_id=1)

		# way out being registered for this ip.
		self.add_flow(datapath, 1,
			parser.OFPMatch(
				eth_type=ipv4_eth,
				ipv4_dst=external_ip,
			),
			[parser.OFPActionOutput(msg.in_port)],
			table_id=2)
			
		dpid = full_dpid(datapath.id)
		print ipv4_pkt.dst
		port = 1 if dpid not in self.entry_map else self.entry_map[dpid][ipv4_pkt.dst]

		# Don't try and guess where this is to go, let the switch deal with it,
		# since it's pre-primed with knowledge of internal routes...
		# note: goto-table is an instr, not action...
		actions=[parser.OFPActionOutput(port)],
		out = ofp_parser.OFPPacketOut(
			datapath=dp, buffer_id=msg.buffer_id, in_port=msg.in_port,
			actions=actions)
		dp.send_msg(out)

# TODO:
# * build groups/starting rules on actor switches/externals
