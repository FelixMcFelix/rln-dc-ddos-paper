#!/bin/bash

echo "Start cap-prep."
#./purger.sh
#python ./feature-test-cap-prep.py
echo "End cap-prep. Start bonus-cap-prep."
./purger.sh
python ./bonus-feature-test-cap-prep.py
echo "End bonus-cap-prep. Start tcp-cap-prep."
./purger.sh
python ./feature-test-tcp-cap-prep.py
echo "End tcp-cap-prep. Start bonus-tcp-cap-prep."
./purger.sh
python ./bonus-feature-test-tcp-cap-prep.py
echo "End bonus-tcp-cap-prep."
./purger.sh

