#!/bin/bash
echo "Bonus capped features: beginning."
./purger.sh
python ./bonus-feature-test-tcp-cap-prep.py
./purger.sh
python ./bonus-feature-test-cap-prep.py
./purger.sh
echo "Bonus capped features: done."
