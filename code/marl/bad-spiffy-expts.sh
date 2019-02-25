#!/bin/bash
SCRIPT="./bad-spif-results.py"

getCount() {
	python $SCRIPT
}
runExpt() {
	python $SCRIPT 0 $1
}

./purger.sh

for i in $(seq 0 $(expr $(getCount) - 1));
do
	./purger.sh
	runExpt $i
done
