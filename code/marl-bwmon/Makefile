CFLAGS=-Wall -Werror -lpcap -lpthread -lsupc++ -std=c++17 -g -O2 -march=native

marl-bwmon: marl-bwmon.cc
	g++ marl-bwmon.cc -o marl-bwmon $(CFLAGS)

clean:
	rm -f marl-bwmon *.o
