#!/bin/bash
#echo "Start tcp-prep."
#./purger.sh
#python ./tcp-model-combo-prep.py
#echo "End tcp-prep. Start tcp-end."
for i in {0..3}
do
	./purger.sh
	python ./tcp-model-combo-end.py $i
	./purger.sh
done
echo "End tcp-end."
