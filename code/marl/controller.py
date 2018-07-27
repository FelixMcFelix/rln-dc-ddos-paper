from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_4

# First, need to make sure we have a parser/formatter for probdrop...
# Remember, its code is 29 and it takes a u32 as input.

# Second, we need a class to spit out rules to make routing happen.
# Assume at first that the router won't make outbound requests in a
# non-trivial way (i.e., don't hash them over outbound ports).

# We somehow need to propagate action information to the controller.
# We also need to figure out if tables are the solution.

class SmartishRouter(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_4.OFP_VERSION]

    # ctor
    def __init__(self, *args, **kwargs):
        super(SmartishRouter, self).__init__(*args, **kwargs)

    # initialisation, post-handshake.
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        n_tables = msg.n_tables

        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        self.logger.debug("Seeing %d tables on dp 0x%016x:"
                            "need 4", n_tables, msg.datapath_id)

        # TODO: this
        # Table 1: (categorisation)
        #   non-local src, local dest -> T2
        #   local src, non-local dest -> T3
        #   miss -> T4
        # Table 2: (register external dests)
        #   ((src ip -> T4))
        #   miss -> packetin
        # Table 3: (external dest routing)
        #   ((dest ip -> output route))
        #   miss -> flood
        # Table 4: (internal dest routing)
        #   dest ip -> output pre-solved

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

        # TODO: this
        # Packet in means we've been notified about a flow (out->in)
        # which has yet to be seen. Record that we've seen it in T2
        # (and forward from T2->T4), and add a flow rule in T3 matching
        # the external destination to the in-port we saw here.

        actions = [ofp_parser.OFPActionOutput(ofp.OFPP_FLOOD)]
        out = ofp_parser.OFPPacketOut(
            datapath=dp, buffer_id=msg.buffer_id, in_port=msg.in_port,
            actions=actions)
        dp.send_msg(out)

