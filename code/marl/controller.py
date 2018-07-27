from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_4
from ryu.lib.packet import packet
from ryu.lib.packet import ipv4

# TODO: controller must know what the experimental parameters are
# i.e. k,l,m,n, subnet, perhaps the entire internal topology?
# Principally, it needs this info to work out directional routing...
# From there, either bfs, floyd-warshall, or chan's algorithm.

ipv4_eth = 0x0800

class SmartishRouter(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_4.OFP_VERSION]

    # ctor
    def __init__(self, *args, **kwargs):
        super(SmartishRouter, self).__init__(*args, **kwargs)
        self.subnet = "10.0.0.0"
        self.netmask = "255.255.255.0"
        self.k = 2
        self.l = 3
        self.m = 2

        # probably open a socket here, and wait to receive params...
        # TODO

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

        # Table 0: (categorisation)
        #   local src, local dest -> T3
        #   local dest -> T1
        #   local src -> T2
        t = 0
        self.add_flow(datapath, 1,
                        parser.OFPMatch(
                            eth_type=ipv4_eth,
                            ipv4_src=local,
                            ipv4_dest=local,
                        ),
                        [parser.OFPInstructionGotoTable(3)],
                        table_id=t)
        self.add_flow(datapath, 1,
                        parser.OFPMatch(
                            eth_type=ipv4_eth,
                            ipv4_dest=local,
                        ),
                        [parser.OFPInstructionGotoTable(1)],
                        table_id=t)
        self.add_flow(datapath, 1,
                        parser.OFPMatch(
                            eth_type=ipv4_eth,
                            ipv4_src=local,
                        ),
                        [parser.OFPInstructionGotoTable(2)],
                        table_id=t)


        # Table 1: (register external dests)
        #   ((src ip -> T3))
        #   miss -> controller
        t = 1
        self.table_miss(datapath,
                        [parser.OFPActionOutput(ofp.OFPP_CONTROLLER)],
                        table_id=t)

        # Table 2: (external dest routing)
        #   ((dest ip -> output route))
        #   miss -> flood
        t = 2
        self.table_miss(datapath,
                        [parser.OFPActionOutput(ofp.OFPP_FLOOD)],
                        table_id=t)

        # Table 3: (internal dest routing)
        #   dest ip -> output pre-solved
        t = 3
        # TODO: presolve according to what we know...

    def add_flow(self, datapath, priority, match, actions, table_id=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # construct flow_mod message and send it.
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                match=match, instructions=inst)
        datapath.send_msg(mod)

    def table_miss(self, datapath, actions, table_id=0):
        self.add_flow(datapath, 0, parser.OFPMatch(), actions,
                        table_id=table_id)

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
                        [parser.OFPInstructionGotoTable(3)],
                        table_id=1)

        # way out being registered for this ip.
        self.add_flow(datapath, 1,
                        parser.OFPMatch(
                            eth_type=ipv4_eth,
                            ipv4_dest=external_ip,
                        ),
                        [parser.OFPActionOutput(msg.in_port)],
                        table_id=2)

        # Don't try and guess where this is to go, let the switch deal with it,
        # since it's pre-primed with knowledge of internal routes...
        actions = [parser.OFPInstructionGotoTable(3)]
        out = ofp_parser.OFPPacketOut(
            datapath=dp, buffer_id=msg.buffer_id, in_port=msg.in_port,
            actions=actions)
        dp.send_msg(out)

# TODO:
# * Compute topology and IP numbering
# * try and figure out how to get from dpid back to IP 
#   (NOTE: ADDRESS AS VISIBLE HERE IS LOCALHOST...) [probably need to include
#   this in a topology graph obtained from the experiment setup]
# * build groups/starting rules on actor switches/externals
