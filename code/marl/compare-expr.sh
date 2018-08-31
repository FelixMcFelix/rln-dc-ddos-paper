#!/bin/bash
#for count in 2 4 7 11 14;
for name in "online-expr-2" "all-udp" "baseline-2" "online-expr-2-nginx" "online-expr-2-e-8";
do
	python "$name.py"
done

