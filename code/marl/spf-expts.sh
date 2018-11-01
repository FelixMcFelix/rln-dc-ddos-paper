#!/bin/bash
SCRIPT="./big-final-results.py"

getCount() {
	python $SCRIPT
}
runExpt() {
	python $SCRIPT 1 $1
}

./purger.sh

for i in $(seq 0 $(expr $(getCount) - 1));
do
	runExpt $i
	./purger.sh
done
