from mininet.topo import Topo
from mininet.node import OVSSwitch, RemoteController
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.net import Mininet
from mininet.clean import Cleanup

linkopts = {"bw": 10}

# Maaaaan forget all of that for now.

# class MarlTest(Topo):

# 	def __init__(self):
# 		# Initialize topology
# 		Topo.__init__(self)

# 		# Make some switches
# 		Topo.addSwitch()

# topos = { 'marltest': ( lambda: MarlTest() ) }

Cleanup.cleanup()

net = Mininet(link=TCLink)#, autoStaticArp=True)

# Turns out this is real important. Whoooops...
net.addController("c0", controller=RemoteController, ip="127.0.0.1", port=6633)

# Okay, switches exist and have a tree like topology (s1 is the "head")
# Suppose for now hat they all have the same (low) bandwidth.
switches = [net.addSwitch("s{}".format(i)) for i in xrange(3)]
hosts = [net.addHost("h{}".format(i)) for i in xrange(3)]
links = []

def trackedLink(src, target):
	links.append(net.addLink(src, target, **linkopts))
	# print "New link between {} and {}!".format(src.name, target.name)

def maybeLink(target):
	if target <= len(switches):
		si = int(target/2)-1
		ti = target-1
		trackedLink(switches[si], switches[ti])

for i, el in enumerate(switches):
	ti = i + 1
	maybeLink(2*ti)
	maybeLink(2*ti + 1)

# Fix this later to target head, then leaves.
for i in xrange(3):
	trackedLink(hosts[i], switches[i])

net.start()

net.waitConnected()
#CLI(net)

for i, sw in enumerate(switches):
	sw.sendCmd("python", "agent.py", i, linkopts["bw"], ">", "{}.txt".format(i))

#net.iperf((hosts[1],hosts[2]))
#net.iperf((hosts[0],hosts[1]))
#net.iperf((hosts[0],hosts[2]))

CLI(net)

net.stop()
