set terminal tikz standalone color size 9cm,6cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage{times} \usepackage[T1]{fontenc} \usepackage{siunitx}\sisetup{detect-all}'
set output "ftprep-tcp-cap-good-3.tex"

load "inferno.pal"

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
set key inside top right

plot '../results/baseline-2-avg-ng.csv' u 1:3 w lines smooth sbezier title "Baseline" dt 1, \
     '../results/ft-tcp-cap-f8-avg.csv' u 1:3 w lines smooth sbezier title "Packets In" ls 2 dt (18,2,2,2), \
     '../results/ft-tcp-cap-f9-avg.csv' u 1:3 w lines smooth sbezier title "Packets Out" ls 3 dt (6,2,2,2), \
     '../results/ft-tcp-cap-f10-avg.csv' u 1:3 w lines smooth sbezier title "Packets In Window" ls 4 dt (18,2), \
     '../results/ft-tcp-cap-f11-avg.csv' u 1:3 w lines smooth sbezier title "Packets Out Window" ls 5 dt (6,2), \
     '../results/ft-tcp-cap-f12-avg.csv' u 1:3 w lines smooth sbezier title "Mean In Pkt Size" ls 6 dt (2,2), \
     '../results/ft-tcp-cap-f13-avg.csv' u 1:3 w lines smooth sbezier title "Mean Out Pkt Size" ls 7 dt (2,1,1,1), \
