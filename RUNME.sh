#!/bin/bash
git submodule update --init --recursive
touch code/marl/tilecoding/__init__.py
mkdir -p data/pcaps
wget -P data/pcaps https://s3.amazonaws.com/tcpreplay-pcap-files/bigFlows.pcap

cd code/marl-bwmon
make

cd ../traffic-host
./RUNME.sh

cd ../opus-voip-traffic
cargo build --release
