set terminal tikz standalone color size 9cm,6cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage{times} \usepackage[T1]{fontenc} \usepackage{siunitx}\sisetup{detect-all}'
set output "tnsm-algo-spf-tcp.tex"

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
set key outside top horizontal
set key font ",5"

plot '../results/tnsm-tree-16-tcp-spf-separate.avg.csv' u 1:3 w lines smooth sbezier title "Guarded (Sarsa, Separate)" dt 1, \
     '../results/tnsm-algo-tree-16-tcp-spf-separate.avg.csv' u 1:3 w lines smooth sbezier title "Guarded (Q, Separate)" ls 2 dt (18,2,2,2), \
     '../results/algotest-spf-separate-tcp-sarsa-16-0.8-0.8.avg.csv' u 1:3 w lines smooth sbezier title "Guarded (S($\\lambda=0.8$), Separate)" ls 3 dt (6,2,2,2), \
     '../results/algotest-spf-separate-tcp-q-16-0.8-0.8.avg.csv' u 1:3 w lines smooth sbezier title "Guarded (Q($\\lambda=0.8$), Separate)" ls 4 dt (18,2), \
     '../results/tnsm-tree-16-tcp-spf-single.avg.csv' u 1:3 w lines smooth sbezier title "Guarded (Sarsa, Single)" ls 5 dt (6,2), \
     '../results/tnsm-algo-tree-16-tcp-spf-single.avg.csv' u 1:3 w lines smooth sbezier title "Guarded (Q, Single)" ls 6 dt (4,2,2,2), \
     '../results/algotest-spf-single-tcp-sarsa-16-0.8-0.8.avg.csv' u 1:3 w lines smooth sbezier title "Guarded (S($\\lambda=0.8$), Single)" ls 7 dt (4,2), \
     '../results/algotest-spf-single-tcp-q-16-0.8-0.8.avg.csv' u 1:3 w lines smooth sbezier title "Guarded (Q($\\lambda=0.8$), Single)" ls 8 dt (2,2)

# plot '../results/tnsm-tree-16-tcp-m-separate.avg.csv' u 1:3 w lines smooth sbezier title "Marl" dt 1, \
#      '../results/tnsm-tree-16-tcp-mpp-separate.avg.csv' u 1:3 w lines smooth sbezier title "Instant" ls 3 dt (18,2,2,2), \
#      '../results/tnsm-tree-16-tcp-spf-separate.avg.csv' u 1:3 w lines smooth sbezier title "Guarded" ls 5 dt (6,2,2,2), \
#      '../results/tnsm-tree-16-tcp-mpp-single.avg.csv' u 1:3 w lines smooth sbezier title "Instant (Single)" ls 6 dt (18,2), \
#      '../results/tnsm-tree-16-tcp-spf-single.avg.csv' u 1:3 w lines smooth sbezier title "Guarded (Single)" ls 7 dt (6,2), \
#      '../results/tnsm-baseline-ecmp-16-tcp.avg.csv' u 1:3 w lines smooth sbezier title "Unprotected" ls 8 dt (2,2), \