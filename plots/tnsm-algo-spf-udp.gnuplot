set terminal tikz standalone color size 9cm,6cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage{times} \usepackage[T1]{fontenc} \usepackage{siunitx}\sisetup{detect-all}'
set output "tnsm-algo-spf-udp.tex"

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

plot '../results/tnsm-tree-16-opus-spf-separate.avg.csv' u 1:3 w lines smooth sbezier title "Guarded (Sarsa, Sep)" dt (6,2,2,2), \
     '../results/tnsm-algo-tree-16-opus-spf-separate.avg.csv' u 1:3 w lines smooth sbezier title "Guarded (Q, Sep)" dt (6,2,2,2), \
     '../results/tnsm-tree-16-opus-spf-single.avg.csv' u 1:3 w lines smooth sbezier title "Guarded (Sarsa, Single)" dt (6,2), \
     '../results/tnsm-algo-tree-16-opus-spf-single.avg.csv' u 1:3 w lines smooth sbezier title "Guarded (Q, Single)" dt (6,2), \
