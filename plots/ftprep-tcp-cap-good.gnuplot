set terminal tikz standalone color size 9cm,6cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage{times} \usepackage[T1]{fontenc} \usepackage{siunitx}\sisetup{detect-all}'
set output "ftprep-tcp-cap-good.tex"

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
     '../results/ft-tcp-cap-g-avg.csv' u 1:3 w lines smooth sbezier title "4 $\\cdot{}$ Load" dt (18,2,2,2), \
     '../results/ft-tcp-cap-f0-avg.csv' u 1:3 w lines smooth sbezier title "IP" ls 4 dt (6,2,2,2), \
     '../results/ft-tcp-cap-f1-avg.csv' u 1:3 w lines smooth sbezier title "Last Action" ls 5 dt (18,2), \
     '../results/ft-tcp-cap-f2-avg.csv' u 1:3 w lines smooth sbezier title "Duration" ls 6 dt (6,2), \
     '../results/ft-tcp-cap-f3-avg.csv' u 1:3 w lines smooth sbezier title "Flow Size" ls 7 dt (2,2)
