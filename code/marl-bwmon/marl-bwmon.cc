#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <mutex>
#include <shared_mutex>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

#include <arpa/inet.h>
#include <fcntl.h>
#define __STDC_FORMAT_MACROS
#include <inttypes.h>
#include <netinet/in.h>
#include <pcap/pcap.h>
#include <poll.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/un.h>
#include <unistd.h>

namespace ch = std::chrono;

ch::high_resolution_clock::time_point stdifyTimeval(const struct timeval tv) {
	return ch::high_resolution_clock::time_point(
		ch::seconds(tv.tv_sec)
		+ ch::microseconds(tv.tv_usec)
	);
}

const int LISTEN_PORT = 9932;
const bool TIME_PRINT_ERR = false;
const bool USE_UNIX_SOCK = true;
const char *SOCKET_PATH = "bwmon-sock";
const int FLOW_PRUNE_AGE = 2;

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

struct FlowMeasurement {
	int64_t flow_length;
	uint64_t size_in;
	uint64_t size_out;
	uint64_t delta_in;
	uint64_t delta_out;
	uint64_t packets_in_count;
	uint64_t packets_out_count;
	float packets_in_mean;
	float packets_in_variance;
	float packets_out_mean;
	float packets_out_variance;
	float iat_mean;
	float iat_variance;
	uint32_t ip;
};

struct InnerFlowStats
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

	// unseen?
	bool unseen = true;

	InnerFlowStats() {
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
		auto prune_age = ch::seconds(FLOW_PRUNE_AGE);

		// prune here if last packet rx'd was of a certain age,
		// AND there was no info gleaned in this window.
		// Don't print stats in that case.

		auto duration = endTime - flow_start;
		auto silent_duration = endTime - last_entry;

		if (silent_duration > prune_age && last_entry < startTime) {
			return false;
		}

		std::cout
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
			<< interarrivals_window.variance();
		clear();

		flow_size_in_prev = flow_size_in;
		flow_size_out_prev = flow_size_out;

		unseen = false;
		return true;
	}

	std::optional<std::pair<bool, FlowMeasurement>> clearAndRetrieveStats(uint32_t ip, char *ip_str, ch::high_resolution_clock::time_point startTime, ch::high_resolution_clock::time_point endTime) {
		auto prune_age = ch::seconds(FLOW_PRUNE_AGE);

		// prune here if last packet rx'd was of a certain age,
		// AND there was no info gleaned in this window.
		// Don't print stats in that case.

		auto duration = endTime - flow_start;
		auto silent_duration = endTime - last_entry;

		if (silent_duration > prune_age && last_entry < startTime) {
			return std::nullopt;
		}

		auto fm = FlowMeasurement {
			ch::nanoseconds(duration).count(),
			flow_size_in,
			flow_size_out,
			flow_size_in - flow_size_in_prev,
			flow_size_out - flow_size_out_prev,
			in_packets_window.k,
			out_packets_window.k,
			(float) in_packets_window.mean,
			(float) in_packets_window.variance(),
			(float) out_packets_window.mean,
			(float) out_packets_window.variance(),
			(float) interarrivals_window.mean,
			(float) interarrivals_window.variance(),
			ip,
		};

		flow_size_in_prev = flow_size_in;
		flow_size_out_prev = flow_size_out;

		auto new_data = unseen;
		unseen = false;

		return std::optional<std::pair<bool, FlowMeasurement>> {std::make_pair(new_data, fm)};
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

struct FlowStats
{
	std::unordered_map<uint32_t, InnerFlowStats> per_dest_stats_;

	FlowStats() {
		//interarrivals.report_update = true;
	};

	void update(ch::high_resolution_clock::time_point arr_time, uint64_t size, bool inbound, uint32_t internal_ip) {		// get the entry using internal_ip, then update IT.
		auto it = per_dest_stats_.find(internal_ip);

		if (it != per_dest_stats_.end()) {
			it->second.update(arr_time, size, inbound);
		} else {
			InnerFlowStats new_stat;
			new_stat.update(arr_time, size, inbound);
			per_dest_stats_[internal_ip] = new_stat;
		}
	}

	bool clearAndPrintStats(char *ip_str, ch::high_resolution_clock::time_point startTime, ch::high_resolution_clock::time_point endTime) {
		if (per_dest_stats_.empty()) {
			return false;
		}

		// Note: we'll be told whether we need to prune each internal.
		// If we ever prune everything, then allow self to be pruned.

		std::cout << "(" << ip_str;

		std::vector<uint32_t> to_prune;

		for (auto &it : per_dest_stats_) {
			auto internal = it.first;

			char internal_ip_str[INET_ADDRSTRLEN];
			auto c_ip = reinterpret_cast<const in_addr *>(&internal);
			inet_ntop(AF_INET, c_ip, internal_ip_str, INET_ADDRSTRLEN);

			std::cout << "|" << internal_ip_str << ",";

			auto active =
				it.second.clearAndPrintStats(ip_str, startTime, endTime);

			if (!active) {
				to_prune.push_back(internal);
			}
		}

		std::cout << ")";

		for (auto &el : to_prune) {
			per_dest_stats_.erase(el);
		}

		return true;
	}

	std::optional<std::pair<bool, FlowMeasurement>> clearAndRetrieveStats(uint32_t ip, char *ip_str, ch::high_resolution_clock::time_point startTime, ch::high_resolution_clock::time_point endTime) {
		// auto prune_age = ch::seconds(FLOW_PRUNE_AGE);

		// // prune here if last packet rx'd was of a certain age,
		// // AND there was no info gleaned in this window.
		// // Don't print stats in that case.

		// auto duration = endTime - flow_start;
		// auto silent_duration = endTime - last_entry;

		// if (silent_duration > prune_age && last_entry < startTime) {
		// 	return std::nullopt;
		// }

		// auto fm = FlowMeasurement {
		// 	ch::nanoseconds(duration).count(),
		// 	flow_size_in,
		// 	flow_size_out,
		// 	flow_size_in - flow_size_in_prev,
		// 	flow_size_out - flow_size_out_prev,
		// 	in_packets_window.k,
		// 	out_packets_window.k,
		// 	(float) in_packets_window.mean,
		// 	(float) in_packets_window.variance(),
		// 	(float) out_packets_window.mean,
		// 	(float) out_packets_window.variance(),
		// 	(float) interarrivals_window.mean,
		// 	(float) interarrivals_window.variance(),
		// 	ip,
		// };

		// clear();

		// flow_size_in_prev = flow_size_in;
		// flow_size_out_prev = flow_size_out;

		// auto new_data = unseen;
		// unseen = false;

		// return std::optional<std::pair<bool, FlowMeasurement>> {std::make_pair(new_data, fm)};

		// FIXME
		return std::nullopt;
	}
};

struct ValueSet {
	ch::high_resolution_clock::time_point time;
	int64_t duration_ns;
	std::vector<uint64_t> good_bytes;
	std::vector<uint64_t> bad_bytes;
	std::vector<std::vector<FlowMeasurement>> flows;
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

	void incrementStat(uint32_t internal_ip, uint32_t external_ip, int interface, bool good, uint32_t packetSize, bool inbound, ch::high_resolution_clock::time_point arr_time) {
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
			auto it = stat_holder.find(external_ip);

			if (it != stat_holder.end()) {
				it->second.update(arr_time, packetSize, inbound, internal_ip);
			} else {
				FlowStats new_stat;
				new_stat.update(arr_time, packetSize, inbound, internal_ip);
				stat_holder[external_ip] = new_stat;
			}
		}
	}

	ValueSet clearAndRetrieveStats(ch::high_resolution_clock::time_point startTime, std::vector<uint32_t> &allowed_ips) {
		std::unique_lock<std::shared_mutex> lock(mutex_);

		auto endTime = ch::high_resolution_clock::now();
		auto duration = endTime - startTime;

		// First, tell the threads they have a limit TO WORK UP TO.
		limiting_ = true;
		limit_ = endTime;
		to_go_.store(num_interfaces_);

		// Okay, now await the signal from all the workers...
		int t_g = num_interfaces_;
		while ((t_g = to_go_.load()) > 0) {
			hit_limit_.wait(lock);
		}

		// Then, we need to wait for them to finish before we do all this...
		auto duration_ns = ch::nanoseconds(duration).count();
		auto goods = good_byte_counts_;
		auto bads = bad_byte_counts_;
		auto flows = std::vector<std::vector<FlowMeasurement>>();

		// capture all relevant flow info...
		// use allowed_ips
		for (unsigned int i = 0; i < flow_stats_.size(); ++i)
		{
			if (!isImportant(i)) {
				continue;
			}

			auto &ip_map = flow_stats_.at(i);
			auto to_prune = std::vector<uint32_t>();
			auto local_flows = std::vector<FlowMeasurement>();

			for (auto &el: ip_map) {
				char ip_str[INET_ADDRSTRLEN];
				auto c_ip = reinterpret_cast<const in_addr *>(&el.first);
				inet_ntop(AF_INET, c_ip, ip_str, INET_ADDRSTRLEN);

				auto maybe_flow_stat = el.second.clearAndRetrieveStats(el.first, ip_str, startTime, endTime);
				if (maybe_flow_stat == std::nullopt) {
					to_prune.emplace_back(el.first);
				} else {
					auto d = maybe_flow_stat.value();
					// Need to bypass this if flow is new.
					if (d.first || std::find(allowed_ips.begin(), allowed_ips.end(), el.first) != allowed_ips.end()) {
						local_flows.emplace_back(d.second);
					}
				}
			}
			flows.emplace_back(local_flows);

			for (auto &ip: to_prune) {
				ip_map.erase(ip);
			}
		}

		// Empty the stats.
		for (auto &el: good_byte_counts_)
			el = 0;
		for (auto &el: bad_byte_counts_)
			el = 0;

		limiting_ = false;

		// Signal done.
		stopped_limiting_.notify_all();

		return ValueSet {
			endTime,
			duration_ns,
			goods,
			bads,
			flows,
		};
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

			//std::cerr << "C: " << i << std::endl;
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

static uint32_t make_netmask(int len) {
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
	uint32_t external_ip = 0;
	uint32_t internal_ip = 0;

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
			external_ip = outbound
				? dst_ip
				: src_ip;
			internal_ip = outbound
				? src_ip
				: dst_ip;

			// Another assumption, we're little endian.
			// this is only troublesome
			good = !(((external_ip>>24)&0xff) % 2);

			break;
		}
		case DLT_RAW:
			std::cout << "ip linktype" << std::endl;
			break;
		default:
			std::cerr << "Unknown linktype for iface "
				<< params->index << ": saw " << params->linkType << std::endl;
	}

	params->stats.incrementStat(internal_ip, external_ip, params->index, good, h->len, !outbound, arr_time);
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


static bool read_val(int fd, void *location, size_t len, InterfaceStats &stats) {
	auto remaining = len;
	auto err = false;

	timeval tv;
	fd_set selector;

	while (remaining && !err) {
		tv.tv_sec = 1;
		tv.tv_usec = 0;

		FD_ZERO(&selector);
		FD_SET(fd, &selector);
		select(fd + 1, &selector, nullptr, nullptr, &tv);

		auto bytes_read = 0;

		if (FD_ISSET(fd, &selector)) {
			bytes_read = recv(
				fd,
				(reinterpret_cast<char *>(location)) + (len - remaining),
				remaining,
				0
			);
		}

		if (bytes_read < 0 || stats.finished()) {
			err = true;
			break;
		} else {
			remaining -= bytes_read;
		}
	}

	return err;
}

static bool send_val(int fd, void *location, size_t len, InterfaceStats &stats) {
	auto remaining = len;
	auto err = false;

	while (remaining && !err) {
		auto bytes_sent = 0;
		bytes_sent = send(
			fd,
			(reinterpret_cast<char *>(location)) + (len - remaining),
			remaining,
			0
		);

		if (bytes_sent < 0 || stats.finished()) {
			err = true;
			break;
		} else {
			remaining -= bytes_sent;
		}
	}

	return err;
}

static void server_runner(InterfaceStats &stats) {
	auto startTime = ch::high_resolution_clock::now();

	int server_fd;
	sockaddr_in address, remote;
	sockaddr_un u_address;
	auto opt = 1;

	if (!USE_UNIX_SOCK){
		if (!(server_fd = socket(PF_INET, SOCK_STREAM, 0))) {
			perror("couldn't create socket");
			exit(EXIT_FAILURE);
		}
	} else {
		if (!(server_fd = socket(PF_LOCAL, SOCK_STREAM, 0))) {
			perror("couldn't create socket");
			exit(EXIT_FAILURE);
		}
	}

	if(setsockopt(
			server_fd,
			SOL_SOCKET,
			SO_REUSEADDR | SO_REUSEPORT | SO_KEEPALIVE,
			&opt,
			sizeof(opt))) {
		perror("couldn't set socket options");
		close(server_fd);
		exit(EXIT_FAILURE);
	}

	address.sin_family = AF_INET;
	address.sin_addr.s_addr = INADDR_ANY;
	address.sin_port = htons(LISTEN_PORT);

	memset(&u_address, 0, sizeof(u_address));
	u_address.sun_family = AF_UNIX;
	strncpy(u_address.sun_path, SOCKET_PATH, sizeof(u_address.sun_path)-1);

	if (!USE_UNIX_SOCK) {
		if (bind(server_fd, (sockaddr *)&address, sizeof(address)) < 0) {
			perror("failed to bind port...");
			close(server_fd);
			exit(EXIT_FAILURE);
		}
	} else {
		unlink(SOCKET_PATH);
		if (bind(server_fd, (sockaddr *)&u_address, sizeof(u_address)) < 0) {
			perror("failed to bind port...");
			close(server_fd);
			exit(EXIT_FAILURE);
		}
	}
	if (listen(server_fd, 1) < 0) {
		perror("failed to listen on local address");
		close(server_fd);
		exit(EXIT_FAILURE);
	}

	// First, select the fd with a timeout.
	// Accept if it didn't time out.
	// Don't accept a new conn if stats.finished()
	// and break out of a conn if the whole shebang ended.
	// (Note: only doing 1 connection at the moment.)
	// (Probably need non-blocking sockets?)
	unsigned int addr_sz = sizeof(remote);
	auto new_conn = accept4(server_fd, (sockaddr *)&remote, &addr_sz, SOCK_NONBLOCK);
	if (new_conn < 0) {
		perror("failed to listen on local address");
		close(server_fd);
		exit(EXIT_FAILURE);
	}

	// Loop on reads, exit on stats.finished()
	while (!stats.finished()) {
		// read a u32. (network order).
		uint32_t n_flow_queries;

		if (read_val(new_conn, &n_flow_queries, sizeof(n_flow_queries), stats)) {
			break;
		}

		n_flow_queries = ntohl(n_flow_queries);

		// read that many IP addresses now.
		auto flow_ips = std::vector<uint32_t>(n_flow_queries);
		auto fip_size = n_flow_queries * sizeof(uint32_t);

		if (read_val(new_conn, flow_ips.data(), fip_size, stats)) {
			break;
		}
		auto inTime = ch::high_resolution_clock::now();

		// Hacky -- assumes both ends are IEEE-754 compliant floats.
		// This should give us everything we need though, gcc won't
		// reorder structs thankfully.
		auto stat_block = stats.clearAndRetrieveStats(startTime, flow_ips);

		// send time since last read in ns...
		if (send_val(new_conn, &stat_block.duration_ns, sizeof(int64_t), stats)) {
			break;
		}

		// Okay, send byte values for all the standard loads...
		for (auto b_val : stat_block.good_bytes) {
			if (send_val(new_conn, &b_val, sizeof(uint64_t), stats)) {
				goto escape;
			}
		}
		for (auto b_val : stat_block.bad_bytes) {
			if (send_val(new_conn, &b_val, sizeof(uint64_t), stats)) {
				goto escape;
			}
		}

		// And now, use the acquired ip addresses to
		// ping along the relevant stat blocks!
		for (auto &flow : stat_block.flows) {
			auto n_flows = (uint32_t) flow.size();
			auto prep = htonl(n_flows);
			if (send_val(new_conn, &prep, sizeof(uint32_t), stats)) {
				goto escape;
			}
			if (n_flows < 1) {
				continue;
			}
			if (send_val(new_conn, flow.data(), n_flows * sizeof(FlowMeasurement), stats)) {
				goto escape;
			}
		}

		startTime = stat_block.time;
		auto outTime = ch::high_resolution_clock::now();
		if (TIME_PRINT_ERR) {
			std::cerr << "C-time:" << ch::nanoseconds(outTime - inTime).count()/1000000 << std::endl;
		}
	}

	// Donezo.
escape:
	shutdown(new_conn, SHUT_RDWR);
	close(new_conn);
	close(server_fd);
	std::this_thread::yield();
}

static void do_join(std::thread& t)
{
	t.join();
}

static void listDevices(char *errbuf) {
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
	auto start_pos = 1;
	auto server = false;

	std::vector<std::thread> workers;

	// catch server flag
	if (num_interfaces > 0 && !strcmp("-s", argv[start_pos])) {
		server = true;
		start_pos += 1;
		num_interfaces -= 1;
	}

	if (num_interfaces == 0) {
		listDevices(errbuf);
		printf("Struct size? %" PRIu64 "\n", sizeof(FlowMeasurement));
		return 0;
	}

	auto stats = InterfaceStats(num_interfaces);
	auto startTime = ch::high_resolution_clock::now();

	bool err = false;

	for (int i = 0; i < num_interfaces; ++i)
	{
		// iterate over iface names, spawn threads!
		// We want to catch any which start with a '!', these are]
		// important 
		auto name = argv[start_pos + i];
		auto individual_stats = name[0]=='!';
		if (individual_stats) {
			name = &(name[1]);
			stats.markImportant(i);
		}

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

	// If we're doing the server thing, we want a thread running that.
	// Its job is to handle connections (one at a time, allowing reconnection),
	// and respond to more granular stat requests as they come in.
	if (server) {
		workers.emplace_back(std::thread(server_runner, std::ref(stats)));
	}

	// Now block on next user input.
	std::string lineInput;

	if (!err){
		while (1) {
			// Any (non-EOF) line will produce more output.
			std::getline(std::cin, lineInput);

			if (std::cin.eof()) break;

			if (!server) {
				auto inTime = ch::high_resolution_clock::now();
				startTime = stats.clearAndPrintStats(startTime);
			
				auto outTime = ch::high_resolution_clock::now();
				if (TIME_PRINT_ERR) {
					std::cerr << "C-time:" << ch::nanoseconds(outTime - inTime).count()/1000000 << std::endl;
				}
			}
		}
	}

	// Kill and cleanup if they send a signal or whatever.
	stats.signalEnd();
	std::for_each(workers.begin(), workers.end(), do_join);
		
	return 0;
}
