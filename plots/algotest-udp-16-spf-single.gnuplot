set terminal tikz standalone color size 9cm,6cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage{times} \usepackage[T1]{fontenc} \usepackage{siunitx}\sisetup{detect-all}'
set output "algotest-udp-16-spf-single.tex"

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

plot '../results/algotest-spf-single-udp-sarsa-16-0.8-0.0.avg.csv' u 1:3 w lines smooth sbezier title "Sarsa 0.0" dt 1, \
     '../results/algotest-spf-single-udp-sarsa-16-0.8-0.2.avg.csv' u 1:3 w lines smooth sbezier title "Sarsa 0.2" ls 2 dt (18,2,2,2), \
     '../results/algotest-spf-single-udp-sarsa-16-0.8-0.4.avg.csv' u 1:3 w lines smooth sbezier title "Sarsa 0.4" ls 3 dt (6,2,2,2), \
     '../results/algotest-spf-single-udp-sarsa-16-0.8-0.6.avg.csv' u 1:3 w lines smooth sbezier title "Sarsa 0.6" ls 4 dt (18,2), \
     '../results/algotest-spf-single-udp-sarsa-16-0.8-0.8.avg.csv' u 1:3 w lines smooth sbezier title "Sarsa 0.8" ls 5 dt (6,2), \
     '../results/algotest-spf-single-udp-q-16-0.8-0.0.avg.csv' u 1:3 w lines smooth sbezier title "Q 0.0" ls 6 dt 1, \
     '../results/algotest-spf-single-udp-q-16-0.8-0.2.avg.csv' u 1:3 w lines smooth sbezier title "Q 0.2" ls 7 dt (18,2,2,2), \
     '../results/algotest-spf-single-udp-q-16-0.8-0.4.avg.csv' u 1:3 w lines smooth sbezier title "Q 0.4" ls 8 dt (6,2,2,2), \
     '../results/algotest-spf-single-udp-q-16-0.8-0.6.avg.csv' u 1:3 w lines smooth sbezier title "Q 0.6" ls 9 dt (18,2), \
     '../results/algotest-spf-single-udp-q-16-0.8-0.8.avg.csv' u 1:3 w lines smooth sbezier title "Q 0.8" ls 10 dt (6,2)
