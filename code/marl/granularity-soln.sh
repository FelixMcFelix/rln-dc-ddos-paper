#!/bin/bash
# for count in 2 4 8 16;
for count in 2 4 8;
do
	#python "soln-$count.py"
	#python "soln-cap-$count.py"
done

for count in 2 4 8;
do
	python "soln-ext-cap-$count.py"
done

#for count in 2 4 8;
for count in 8;
do
	python "soln-ext-$count.py"
done
