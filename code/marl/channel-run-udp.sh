#!/bin/bash

#tests=(0 3)
#tests=(1 2)
tests=(0 1 2 3)

for v in "${tests[@]}"
do
	./purger.sh
	python ./udp-model-combo-channel-prep.py $v
	./purger.sh
	python ./udp-model-combo-channel-prep.py $v "prog"
	./purger.sh
	python ./udp-model-combo-channel-end.py $v
	./purger.sh
done
