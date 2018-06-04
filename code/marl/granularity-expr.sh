#!/bin/bash
for count in 2 7 11 14;
do
	python "online-expr-$count.py"
	python "online-expr-$count-even.py"
done

