set terminal tikz standalone color size 9cm,6cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage{times} \usepackage[T1]{fontenc} \usepackage{siunitx}\sisetup{detect-all}'
set output "ftprep-tcp-cap-reward.tex"

load "parula.pal"

set style line 102 lc rgb '#a0a0a0' lt 1 lw 1
set border ls 102
set colorbox border 102
set key textcolor rgb "black"
set tics textcolor rgb "black"
set label textcolor rgb "black"

set border 3
set grid x y
set xtics nomirror
set ytics nomirror

#set key autotitle columnhead
set datafile separator ","

set xlabel "Iteration ($t \\cdot{} \\SI{50}{\\milli\\second}$)"
set ylabel "Reward"

set yrange [-1.0:1.0]

plot '../results/baseline-2-avg-ng.csv' u 1:2 w lines smooth sbezier title "baseline", \
     '../results/ft-tcp-cap-g-avg.csv' u 1:2 w lines smooth sbezier title "G", \
     '../results/ft-tcp-cap-f0-avg.csv' u 1:2 w lines smooth sbezier title "f0", \
     '../results/ft-tcp-cap-f1-avg.csv' u 1:2 w lines smooth sbezier title "f1", \
     '../results/ft-tcp-cap-f2-avg.csv' u 1:2 w lines smooth sbezier title "f2", \
     '../results/ft-tcp-cap-f3-avg.csv' u 1:2 w lines smooth sbezier title "f3"
