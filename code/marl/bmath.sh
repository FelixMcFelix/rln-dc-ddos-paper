#!/bin/bash
SCRIPT="./bmath-results.py"

getCount() {
	python $SCRIPT
}
runExpt() {
	python $SCRIPT $1 $2
}

./purger.sh

#for i in $(seq 0 1);
#do
	for j in $(seq 0 $(expr $(getCount) - 1));
	do
		#runExpt $i $j
		runExpt 0 $j
		./purger.sh
	done
#done
