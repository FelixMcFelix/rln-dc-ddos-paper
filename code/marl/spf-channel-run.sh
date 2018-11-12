#!/bin/bash

tests=(0 1 2 3)

for v in "${tests[@]}"
do
	./purger.sh
	python ./tcp-spf-combo-channel-prep.py $v
	./purger.sh
	python ./tcp-spf-combo-channel-prep.py $v "prog"
	./purger.sh
	python ./tcp-spf-combo-channel-end.py $v
	./purger.sh
	python ./udp-spf-combo-channel-prep.py $v
	./purger.sh
	python ./udp-spf-combo-channel-prep.py $v "prog"
	./purger.sh
	python ./udp-spf-combo-channel-end.py $v
	./purger.sh
done
