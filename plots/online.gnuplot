set key autotitle columnhead
set datafile separator ","

plot '../results/online-standard-avg.csv' u 1:3 w lines, \
     '../results/online-mod-avg.csv' u 1:3 w lines