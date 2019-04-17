#!/bin/bash
function purgeprocs {
	ps ax | grep "$1" | awk -F ' ' '{print $1}' | xargs sudo kill -9
	#echo "$1"
}

purgeprocs nginx
purgeprocs hping3
purgeprocs traffic-host
purgeprocs tcpreplay-edit
purgeprocs marl-bwmon
purgeprocs ryu-manager
purgeprocs opus-voip-traffic

