#!/bin/bash
# for count in 2 4 8 16;
# for count in 4 8 16;
# do
# 	python "soln-$count.py"
# done

#for count in 2 4 8 16;
#do
#	python "online-expr-$count-e-8.py"
#done
#for count in 2 4 8;
#do
#	python "soln-ext-cap-$count.py"
#done

./purger.sh
python bmath-results.py 0 1
./purger.sh
./marl-expts.sh
./purger.sh
