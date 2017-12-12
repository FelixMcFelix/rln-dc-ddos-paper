#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <mutex>
#include <shared_mutex>
#include <string>
#include <thread>
#include <vector>

#include <pcap/pcap.h>

class InterfaceStats
{
public:
	InterfaceStats(int numInterfaces) {
		bad_byte_counts_ = std::vector<uint64_t>(numInterfaces, 0);
		good_byte_counts_ = std::vector<uint64_t>(numInterfaces, 0);
	}

	void incrementStat(int interface, bool good, uint32_t packetSize) {
		std::shared_lock<std::shared_mutex> lock(mutex_);

		if (good) 
			good_byte_counts_[interface] += packetSize;
		else
			bad_byte_counts_[interface] += packetSize;
	}

	void clearAndPrintStats() {
		std::unique_lock<std::shared_mutex> lock(mutex_);
		
		for (unsigned int i = 0; i < bad_byte_counts_.size(); ++i)
		{
			if (i > 0) std::cout << ", ";

			std::cout << good_byte_counts_[i] << " " << bad_byte_counts_[i];
		}

		std::cout << std::endl;

		for (auto &el: good_byte_counts_)
			el = 0;
		for (auto &el: bad_byte_counts_)
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
	std::vector<uint64_t> bad_byte_counts_;
	std::vector<uint64_t> good_byte_counts_;
	bool end_ = false;
	mutable std::shared_mutex mutex_;
};

static void monitorInterface(pcap_t *iface, const int index, InterfaceStats &stats) {
	pcap_activate(iface);

	while (not stats.finished()) {
		// Something. Read pcaps I guess.
		stats.incrementStat(index, true, 64);
		stats.incrementStat(index, false, 32);
	}

	pcap_close(iface);
	std::this_thread::yield();
}

void do_join(std::thread& t)
{
	t.join();
}

int main(int argc, char const *argv[])
{
	char errbuf[PCAP_ERRBUF_SIZE];
	auto numInterfaces = argc - 1;
	auto stats = InterfaceStats(numInterfaces);

	std::vector<std::thread> workers;

	for (int i = 0; i < numInterfaces; ++i)
	{
		/* iterate over iface names, spawn threads! */
		auto p = pcap_create(argv[i+1], errbuf);

		// Can't copy or move these for whatever reason, so must emplace.
		// i.e. init RIGHT IN THE VECTOR
		workers.emplace_back(std::thread(monitorInterface, p, i, std::ref(stats)));
	}

	// Now block on next user input.

	// Sleep for now while I figure out the best way to do that.
	{
		using namespace std::chrono_literals;
		std::this_thread::sleep_for(5s);
	}
	stats.clearAndPrintStats();

	// Kill and cleanup if they send a signal or whatever.
	stats.signalEnd();
	std::for_each(workers.begin(), workers.end(), do_join);
		
	return 0;
}