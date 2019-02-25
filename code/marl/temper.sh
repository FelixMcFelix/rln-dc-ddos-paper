#!/bin/bash

echo "Start cap-prep."
python ./feature-test-cap-prep.py
echo "End cap-prep. Start cap-end."
python ./feature-test-cap-end.py
echo "End cap-end. Start ftprep."
python ./feature-test-prep.py
echo "End ftprep. Start ftend."
python ./feature-test-end.py
echo "End ftend."

