#!/bin/sh
for iter in 0 1 2 3 4
do
	python spf-d$iter.py
	./purger.sh
done
