#!/bin/bash
SCRIPT="./tnsm-results.py"
Scripts=( "./tnsm-results-highrate.py" "./tnsm-results-highdensity.py" "./tnsm-results-highdensitylowwidth.py" )
#Scripts=( "./tnsm-results-highdensity.py" "./tnsm-results-highdensitylowwidth.py" )

getCount() {
	python $2 $1
}
runExpt() {
	python $3 $1 $2
}

./purger.sh

for s in ${Scripts[*]};
do
	for i in $(seq 0 $(expr $(getCount 0 $s) - 1));
	do
		./purger.sh
		runExpt 0 $i $s
	done
done

./purger.sh

