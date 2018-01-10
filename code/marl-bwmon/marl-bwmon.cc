#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <mutex>
#include <shared_mutex>
#include <string>
#include <thread>
#include <vector>

#include <netinet/in.h>
#include <arpa/inet.h>

#include <pcap/pcap.h>

class InterfaceStats
{
public:
	InterfaceStats(int numInterfaces) {
		badByteCounts_ = std::vector<uint64_t>(numInterfaces, 0);
		goodByteCounts_ = std::vector<uint64_t>(numInterfaces, 0);
	}

	void incrementStat(int interface, bool good, uint32_t packetSize) {
		std::shared_lock<std::shared_mutex> lock(mutex_);

		if (good) 
			goodByteCounts_[interface] += packetSize;
		else
			badByteCounts_[interface] += packetSize;
	}

	void clearAndPrintStats(std::chrono::high_resolution_clock::time_point startTime) {
		std::unique_lock<std::shared_mutex> lock(mutex_);

		auto endTime = std::chrono::high_resolution_clock::now();
		auto duration = endTime - startTime;

		std::cout << std::chrono::nanoseconds(duration).count() << "ns";
		
		for (unsigned int i = 0; i < badByteCounts_.size(); ++i)
		{
			std::cout << ", ";

			std::cout << goodByteCounts_[i] << " " << badByteCounts_[i];
		}

		std::cout << std::endl;

		// Empty the stats.
		for (auto &el: goodByteCounts_)
			el = 0;
		for (auto &el: badByteCounts_)
			el = 0;
	}

	bool finished() {
		std::shared_lock<std::shared_mutex> lock(mutex_);
		return end_;
	}

	void signalEnd() {
		std::unique_lock<std::shared_mutex> lock(mutex_);
		end_ = true;
	}

private:
	std::vector<uint64_t> badByteCounts_;
	std::vector<uint64_t> goodByteCounts_;
	bool end_ = false;
	mutable std::shared_mutex mutex_;
};

struct PcapLoopParams {
	PcapLoopParams(InterfaceStats &s, pcap_t *p, int i, int link)
		: stats(s), iface(p), index(i), linkType(link)
	{
	}
	InterfaceStats &stats;
	pcap_t *iface;
	const int index;
	const int linkType;
};

static void perPacketHandle(u_char *user, const struct pcap_pkthdr *h, const u_char *data) {
	PcapLoopParams *params = reinterpret_cast<PcapLoopParams *>(user);

	// Look at the packet, decide good/bad, then increment!
	// Establish the facts: HERE.
	// Okay, we can read up to h->caplen bytes from data.
	bool good = false;

	switch (params->linkType) {
		case DLT_NULL:
			std::cout << "null linktype (?)" << std::endl;
			break;
		case DLT_EN10MB: {
			// jump in 14 bytes, hope for IPv4. Only do v4 because LAZY.
			// Source addr is 12 further octets in.
			auto ip = *reinterpret_cast<const uint32_t *>(data + 26);

			// Another assumption, we're little endian.
			good = !(((ip>>24)&0xff) % 2);

			//struct in_addr addr { s_addr: ip };
			//char ip_str[INET_ADDRSTRLEN];
			//inet_ntop(AF_INET, &addr, ip_str, INET_ADDRSTRLEN);
			//std::cout << "message from: " << ip_str << " " << good << " " << ((ip>>24)&0xff) <<std::endl;
			break;
		}
		case DLT_RAW:
			std::cout << "ip linktype" << std::endl;
			break;
		default:
			std::cerr << "Unknown linktype for iface "
				<< params->index << ": saw " << params->linkType << std::endl;
	}

	params->stats.incrementStat(params->index, good, h->len);

	if (params->stats.finished())
		pcap_breakloop(params->iface);
}

static void monitorInterface(pcap_t *iface, const int index, InterfaceStats &stats) {
	int err = 0;
	if((err = pcap_activate(iface))) {
		std::cerr << "iface " << index << " could not be initialised: ";

		switch (err) {
			case PCAP_ERROR_NO_SUCH_DEVICE:
				std::cerr << "no such device.";
				break;
			case PCAP_ERROR_PERM_DENIED:
				std::cerr << "bad permissions; run as sudo?";
				break;
			default:
				std::cerr << "something unknown.";
		}

		std::cerr << std::endl;
	}

	int linkType = pcap_datalink(iface);
	auto params = PcapLoopParams(stats, iface, index, linkType);

	pcap_loop(iface, -1, perPacketHandle, reinterpret_cast<u_char *>(&params));

	pcap_close(iface);
	std::this_thread::yield();
}

void do_join(std::thread& t)
{
	t.join();
}

void listDevices(char *errbuf) {
	pcap_if_t *devs = nullptr;
	pcap_findalldevs(&devs, errbuf);

	while (devs != nullptr) {
		std::cout << devs->name;
		if (devs->description != nullptr)
			std::cout << ": " << devs->description;

		std::cout << std::endl;
		devs = devs->next;
	}

	pcap_freealldevs(devs);
}

int main(int argc, char const *argv[])
{
	char errbuf[PCAP_ERRBUF_SIZE];
	auto numInterfaces = argc - 1;
	auto stats = InterfaceStats(numInterfaces);

	std::vector<std::thread> workers;

	if (numInterfaces == 0) {
		listDevices(errbuf);
		return 0;
	}

	auto startTime = std::chrono::high_resolution_clock::now();

	bool err = false;

	for (int i = 0; i < numInterfaces; ++i)
	{
		/* iterate over iface names, spawn threads! */
		auto p = pcap_create(argv[i+1], errbuf);

		if (p == nullptr) {
			err = true;
			std::cerr << errbuf << std::endl;
			break;
		}

		// Can't copy or move these for whatever reason, so must emplace.
		// i.e. init RIGHT IN THE VECTOR
		workers.emplace_back(std::thread(monitorInterface, p, i, std::ref(stats)));
	}

	// Now block on next user input.
	std::string lineInput;

	if (!err){
		while (1) {
			// Any (non-EOF) line will produce more output.
			std::getline(std::cin, lineInput);

			if (std::cin.eof()) break;

			stats.clearAndPrintStats(startTime);
			startTime = std::chrono::high_resolution_clock::now();
		}
	}

	// Kill and cleanup if they send a signal or whatever.
	stats.signalEnd();
	std::for_each(workers.begin(), workers.end(), do_join);
		
	return 0;
}
