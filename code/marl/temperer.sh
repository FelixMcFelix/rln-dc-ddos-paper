#!/bin/bash
echo "TCP baselines: rebeginning."
./purger.sh
python ./baseline-2-nginx.py
./purger.sh
python ./baseline-2-uncap-nginx.py
echo "TCP baselines: redone."
echo "Start tcp-prep."
./purger.sh
python ./feature-test-tcp-prep.py
echo "End tcp-prep. Start tcp-end."
./purger.sh
python ./feature-test-tcp-end.py
echo "End tcp-end."
echo "Start tcp-cap-prep."
./purger.sh
python ./feature-test-tcp-cap-prep.py
echo "End tcp-cap-prep. Start tcp-cap-end."
./purger.sh
python ./feature-test-tcp-cap-end.py
echo "End tcp-cap-end."

