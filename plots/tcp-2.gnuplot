set terminal tikz standalone color size 9cm,6cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage{times} \usepackage[T1]{fontenc} \usepackage{siunitx}\sisetup{detect-all}'
set output "tcp-2.tex"

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

plot '../results/online-2-avg-ng.csv' u 1:3 w lines smooth sbezier title "MARL" dt 1, \
     '../results/m-tcp-natural-2' u 1:3 w lines smooth sbezier title "MARL++" ls 3 dt (18,2,2,2), \
     '../results/spf-tcp-banded-2' u 1:3 w lines smooth sbezier title "SPF" ls 4 dt (6,2,2,2), \
     '../results/tcp-combo-channel-2-avg.csv' u 1:3 w lines smooth sbezier title "MARL++ (Pretrain)" ls 6 dt (18,2), \
     '../results/m-tcp-uncap-2' u 1:3 w lines smooth sbezier title "MARL++ (Weird Pretrain)" ls 7 dt (6,2), \
     #'../results/tcp-combo-2-avg.csv' u 1:3 w lines smooth sbezier title "MARL++ (Weird Pretrain)" ls 7 dt (2,2), \
