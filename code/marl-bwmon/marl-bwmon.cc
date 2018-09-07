#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <iostream>
#include <mutex>
#include <shared_mutex>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

#include <arpa/inet.h>
#include <netinet/in.h>
#include <pcap/pcap.h>
#include <poll.h>
#include <sys/select.h>
#include <sys/time.h>

namespace ch = std::chrono;

ch::high_resolution_clock::time_point stdifyTimeval(const struct timeval tv) {
	return ch::high_resolution_clock::time_point(
		ch::seconds(tv.tv_sec)
		+ ch::microseconds(tv.tv_usec)
	);
}

// Store and update some stats about float64s.
struct Stat {
	double total = 0.0;
	double std = 0.0;
	double mean = 0.0;
	uint64_t k = 0;

	bool report_update = false;

	Stat() {}

	void clear() {
		total = 0.0;
		std = 0.0;
		mean = 0.0;
		k = 0;
	}

	// formulae courtesy of https://www.johndcook.com/blog/standard_deviation/
	void update(double value) {
		auto i = k++;
		total += value;

		if (i == 0) {
			mean = value;
			return;
		}
		auto delta = value - mean;
		mean = mean + delta / i;

		auto delta2 = value - mean;
		std = std + delta * delta2;

		if (report_update) {
			std::cout << "sample: " << value
				<< " gave deltas " << delta
				<< " and " << delta2
				<< std::endl;
		}
	}

	double variance() const {
		return k >= 2
			? std / (k - 1)
			: 0.0;
	}
};

struct FlowStats
{
	// flow size
	uint64_t flow_size_in = 0;
	uint64_t flow_size_out = 0;

	// needed for delta rate
	uint64_t flow_size_in_prev = 0;
	uint64_t flow_size_out_prev = 0;

	// packet stats in this window
	Stat in_packets = Stat();
	Stat out_packets = Stat();
	Stat in_packets_window = Stat();
	Stat out_packets_window = Stat();

	// interarrival times
	Stat interarrivals = Stat();
	Stat interarrivals_window = Stat();

	// flow length
	ch::high_resolution_clock::time_point flow_start;
	ch::high_resolution_clock::time_point last_entry;

	FlowStats() {
		//interarrivals.report_update = true;
	};

	void update(ch::high_resolution_clock::time_point arr_time, uint64_t size, bool inbound) {
		auto dbl_size = (double)size;
		ch::duration<double, std::milli> iat = arr_time - last_entry;

		if (inbound) {
			flow_size_in += size;
			in_packets.update(dbl_size);
			in_packets_window.update(dbl_size);

			// for now, only track IATs on inbound packets.
			interarrivals.update(iat.count());
			interarrivals_window.update(iat.count());
		} else {
			flow_size_out += size;
			out_packets.update(dbl_size);
			out_packets_window.update(dbl_size);
		}

		last_entry = arr_time;
	}

	bool clearAndPrintStats(char *ip_str, ch::high_resolution_clock::time_point startTime, ch::high_resolution_clock::time_point endTime) {
		auto prune_age = ch::seconds(10);

		// prune here if last packet rx'd was of a certain age,
		// AND there was no info gleaned in this window.
		// Don't print stats in that case.

		auto duration = endTime - flow_start;
		auto silent_duration = endTime - last_entry;

		if (silent_duration > prune_age && last_entry < startTime) {
			return false;
		}

		std::cout
			<< "(" << ip_str << ","
			<< ch::nanoseconds(duration).count() << ","
			<< flow_size_in << ","
			<< flow_size_out << ","
			<< flow_size_in - flow_size_in_prev << ","
			<< flow_size_out - flow_size_out_prev << ","
			<< in_packets_window.mean << ","
			<< in_packets_window.variance() << ","
			<< in_packets_window.k << ","
			<< out_packets_window.mean << ","
			<< out_packets_window.variance() << ","
			<< out_packets_window.k << ","
			<< interarrivals_window.mean << ","
			<< interarrivals_window.variance()
			<< ")";
		clear();

		flow_size_in_prev = flow_size_in;
		flow_size_out_prev = flow_size_out;

		return true;
	}

	void clear() {
		in_packets_window.clear();
		out_packets_window.clear();
		interarrivals_window.clear();
	}

	void clear_full() {
		clear();
	}
};

class InterfaceStats
{
	int num_interfaces_;
	std::vector<uint64_t> bad_byte_counts_;
	std::vector<uint64_t> good_byte_counts_;

	std::vector<bool> importants_;
	std::vector<std::unordered_map<uint32_t, FlowStats>> flow_stats_;

	bool limiting_ = false;
	ch::high_resolution_clock::time_point limit_;
	std::atomic<int> to_go_ = std::atomic<int>(0);

	bool end_ = false;

	mutable std::shared_mutex mutex_;
	std::condition_variable_any stopped_limiting_;
	std::condition_variable_any hit_limit_;

public:
	InterfaceStats(int n)
		: num_interfaces_(n)
		, bad_byte_counts_(std::vector<uint64_t>(2*n, 0))
		, good_byte_counts_(std::vector<uint64_t>(2*n, 0))
		, importants_(std::vector<bool>(n, false))
		, flow_stats_(std::vector<std::unordered_map<uint32_t, FlowStats> >(n, std::unordered_map<uint32_t, FlowStats>()))
	{ }

	void markImportant(int n) {
		importants_[n] = true;
	}

	bool isImportant(int n) {
		return importants_.at(n);
	}

	void incrementStat(uint32_t ip, int interface, bool good, uint32_t packetSize, bool inbound, ch::high_resolution_clock::time_point arr_time) {
		std::shared_lock<std::shared_mutex> lock(mutex_);

		auto index = 2 * interface + (inbound ? 0 : 1);
		auto important = isImportant(interface);

		if (good) {
			good_byte_counts_[index] += packetSize;
		} else {
			bad_byte_counts_[index] += packetSize;
		}

		if (important) {
			// first things first: check if the target IP has registered flowstats.
			auto &stat_holder = flow_stats_.at(interface);
			auto it = stat_holder.find(ip);

			if (it != stat_holder.end()) {
				it->second.update(arr_time, packetSize, inbound);
			} else {
				FlowStats new_stat;
				new_stat.update(arr_time, packetSize, inbound);
				stat_holder[ip] = new_stat;
			}
		}
	}

	ch::high_resolution_clock::time_point clearAndPrintStats(ch::high_resolution_clock::time_point startTime) {
		std::unique_lock<std::shared_mutex> lock(mutex_);

		auto endTime = ch::high_resolution_clock::now();
		auto duration = endTime - startTime;

		// First, tell the threads they have a limit TO WORK UP TO.
		limiting_ = true;
		limit_ = endTime;
		to_go_.store(num_interfaces_);

		// Okay, now await the signal from all the workers...
		int t_g = num_interfaces_;
		while ((t_g = to_go_.load()) > 0) hit_limit_.wait(lock);

		// Then, we need to wait for them to finish before we do all this...
		std::cout << ch::nanoseconds(duration).count() << "ns";
		
		for (unsigned int i = 0; i < bad_byte_counts_.size(); ++i)
		{
			std::cout << ", ";

			std::cout << good_byte_counts_[i] << " " << bad_byte_counts_[i];
		}

		std::cout << std::endl;

		// print (on a seperate line) the stats that concern the flows at each learner.
		for (unsigned int i = 0; i < flow_stats_.size(); ++i)
		{
			if (!isImportant(i)) {
				continue;
			}

			std::cout << "[";
			auto &ip_map = flow_stats_.at(i);
			auto to_prune = std::vector<uint32_t>();

			for (auto &el: ip_map) {
				// el = (ip_as_u32, FlowStat)
				char ip_str[INET_ADDRSTRLEN];
				auto c_ip = reinterpret_cast<const in_addr *>(&el.first);
				inet_ntop(AF_INET, c_ip, ip_str, INET_ADDRSTRLEN);

				auto active = el.second.clearAndPrintStats(ip_str, startTime, endTime);
				if (!active) {
					to_prune.emplace_back(el.first);
				}
			}

			for (auto &ip: to_prune) {
				ip_map.erase(ip);
			}

			std::cout << "]";
		}

		std::cout << std::endl;

		// Empty the stats.
		for (auto &el: good_byte_counts_)
			el = 0;
		for (auto &el: bad_byte_counts_)
			el = 0;

		limiting_ = false;

		// Signal done.
		stopped_limiting_.notify_all();
		
		return endTime;
	}

	bool finished() {
		std::shared_lock<std::shared_mutex> lock(mutex_);
		return end_;
	}

	void signalEnd() {
		std::unique_lock<std::shared_mutex> lock(mutex_);
		end_ = true;
	}

	void checkCanRecord(const struct timeval tv, const int id) {
		auto tv_convert = stdifyTimeval(tv);

		checkCanRecord(tv_convert, id);
	}

	void checkCanRecord(const ch::high_resolution_clock::time_point tv_convert, const int id) {
		std::shared_lock<std::shared_mutex> lock(mutex_);

		// Need to (if we hit the limit), signal that we *have*,
		// and then await the main thread signalling that it finished its read/write.
		if (limiting_ && tv_convert >= limit_) {
				// Signal.
				to_go_ -= 1;
				hit_limit_.notify_all();

				// Await using our lock and the reader's signal.
				// Don't loop here: the cond is guaranteed to be valid,
				// and control flow MUST escape.
				stopped_limiting_.wait(lock);
		}
	}
};

uint32_t make_netmask(int len) {
	return htonl(0xffffffff << (32 - len));
}

struct PcapLoopParams {
	PcapLoopParams(InterfaceStats &s, pcap_t *p, int i, int link)
		: stats(s), iface(p), index(i), linkType(link)
	{
		this->netmask = make_netmask(24);
		inet_pton(AF_INET, "10.0.0.0", reinterpret_cast<in_addr *>(&this->subnet));
	}
	InterfaceStats &stats;
	pcap_t *iface;
	const int index;
	const int linkType;
	uint32_t subnet;
	uint32_t netmask;

	bool is_ip_local(const uint32_t addr) {
		return (addr & netmask) == subnet;
	}
};

static void perPacketHandle(u_char *user, const struct pcap_pkthdr *h, const u_char *data) {
	PcapLoopParams *params = reinterpret_cast<PcapLoopParams *>(user);
	auto arr_time = stdifyTimeval(h->ts);

	params->stats.checkCanRecord(arr_time, params->index);

	// Look at the packet, decide good/bad, then increment!
	// Establish the facts: HERE.
	// Okay, we can read up to h->caplen bytes from data.
	bool good = false;
	bool outbound = true;
	uint32_t ip = 0;

	switch (params->linkType) {
		case DLT_NULL:
			std::cout << "null linktype (?)" << std::endl;
			break;
		case DLT_EN10MB: {
			// jump in 14 bytes, hope for IPv4. Only do v4 because LAZY.
			// Source addr is 12 further octets in.
			// Dest addr is 16 into IP (adj to src ip.)
			auto src_ip = *reinterpret_cast<const uint32_t *>(data + 26);
			auto dst_ip = *reinterpret_cast<const uint32_t *>(data + 30);

			// If src is local, then assess based on dst.
			outbound = params->is_ip_local(src_ip);
			ip = outbound
				? dst_ip
				: src_ip;

			// Another assumption, we're little endian.
			// this is only troublesome
			good = !(((ip>>24)&0xff) % 2);

			break;
		}
		case DLT_RAW:
			std::cout << "ip linktype" << std::endl;
			break;
		default:
			std::cerr << "Unknown linktype for iface "
				<< params->index << ": saw " << params->linkType << std::endl;
	}

	params->stats.incrementStat(ip, params->index, good, h->len, !outbound, arr_time);
}

static void monitorInterface(pcap_t *iface, const int index, InterfaceStats &stats) {
	int err = 0;
	int fd = 0;
	char errbuff[PCAP_ERRBUF_SIZE];

	if((err =
		pcap_set_immediate_mode(iface, 1)
		|| pcap_activate(iface))
		|| pcap_setnonblock(iface, 1, errbuff))
	{
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

	if (!err) {
		int linkType = pcap_datalink(iface);
		auto params = PcapLoopParams(stats, iface, index, linkType);

		if ((fd = pcap_get_selectable_fd(iface)) < 0)
			std::cerr << "Weirdly, got fd " << fd << "." << std::endl;

		struct pollfd iface_pollfd = {
			fd,
			POLLIN,
			0
		};

		// pcap_loop(iface, -1, perPacketHandle, reinterpret_cast<u_char *>(&params));

		int count_processed = 0;
		while (count_processed >= 0) {
			auto n_evts = poll(&iface_pollfd, 1, 1);

			if (n_evts > 0)
				count_processed = pcap_dispatch(
					iface, -1, perPacketHandle, reinterpret_cast<u_char *>(&params)
				);
			if (n_evts == 0 || !count_processed)
				stats.checkCanRecord(ch::high_resolution_clock::now(), index);

			if (stats.finished()) {
				break;
			}
		}
	} else {
		std::cerr << "Error setting up pcap: " << errbuff << ", " << pcap_geterr(iface) << std::endl;
	}

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
	auto num_interfaces = argc - 1;
	auto stats = InterfaceStats(num_interfaces);

	std::vector<std::thread> workers;

	if (num_interfaces == 0) {
		listDevices(errbuf);
		return 0;
	}

	auto startTime = ch::high_resolution_clock::now();

	bool err = false;

	for (int i = 0; i < num_interfaces; ++i)
	{
		// iterate over iface names, spawn threads!
		// We want to catch any which start with a '!', these are]
		// important 
		auto name = argv[i+1];
		auto individual_stats = name[0]=='!';
		if (individual_stats) {
			name = &(name[1]);
			stats.markImportant(i);
		}

		// TODO: pass knowledge of individual stat gathering to the monitoring child threads.

		auto p = pcap_create(name, errbuf);

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

			startTime = stats.clearAndPrintStats(startTime);
		}
	}

	// Kill and cleanup if they send a signal or whatever.
	stats.signalEnd();
	std::for_each(workers.begin(), workers.end(), do_join);
		
	return 0;
}
