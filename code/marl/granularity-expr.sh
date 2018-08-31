#!/bin/bash
#for count in 2 4 7 11 14;
for count in 2 4 8 16;
do
	python "online-expr-$count.py"
	#python "online-expr-$count-even.py"
done

