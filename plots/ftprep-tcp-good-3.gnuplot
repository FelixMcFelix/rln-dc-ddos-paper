set terminal tikz standalone color size 9cm,6cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage{times} \usepackage[T1]{fontenc} \usepackage{siunitx}\sisetup{detect-all}'
set output "ftprep-tcp-good-3.tex"

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
set ylabel "Ratio Legit Traffic Preserved"

set yrange [0.0:1.0]
set key inside bottom right

plot '../results/baseline-2-avg-ng.csv' u 1:3 w lines smooth sbezier title "Baseline", \
     '../results/ft-tcp-f8-avg.csv' u 1:3 w lines smooth sbezier title "Packets In" ls 2, \
     '../results/ft-tcp-f9-avg.csv' u 1:3 w lines smooth sbezier title "Packets Out" ls 3, \
     '../results/ft-tcp-f10-avg.csv' u 1:3 w lines smooth sbezier title "Packets In Window" ls 4, \
     '../results/ft-tcp-f11-avg.csv' u 1:3 w lines smooth sbezier title "Packets Out Window" ls 5, \
     '../results/ft-tcp-f12-avg.csv' u 1:3 w lines smooth sbezier title "Mean In Pkt Size" ls 6, \
     '../results/ft-tcp-f13-avg.csv' u 1:3 w lines smooth sbezier title "Mean Out Pkt Size" ls 7, \
