set terminal tikz standalone color size 9cm,6cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage{times} \usepackage[T1]{fontenc} \usepackage{siunitx}\sisetup{detect-all}'
set output "algotest-vs-old-tcp.tex"

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
set key inside bottom right

plot '../results/algotest-spf-single-tcp-sarsa-16-0.8-0.0.avg.csv' u 1:3 w lines smooth sbezier title "Sarsa 0.0 (New)" dt 1, \
     '../results/algotest-spf-single-tcp-q-16-0.8-0.0.avg.csv' u 1:3 w lines smooth sbezier title "Q 0.0 (New)" ls 3 dt (18,2,2,2), \
     '../results/spf-tcp-single-16' u 1:3 w lines smooth sbezier title "SPF (Single)" ls 5 dt (6,2,2,2), \
     '../results/spf-tcp-natural-16' u 1:3 w lines smooth sbezier title "SPF (Multi)" ls 6 dt (18,2), \
     '../results/bmath-False.avg.csv' u 1:3 w lines smooth sbezier title "Fixed Math" ls 7 dt (6,2), \
     '../results/bmath-True.avg.csv' u 1:3 w lines smooth sbezier title "Broken Math" ls 8 dt (2,2), \

#plot '../results/online-16-avg-ng.csv' u 1:3 w lines smooth sbezier title "Marl" dt 1, \
#     '../results/m-tcp-natural-16' u 1:3 w lines smooth sbezier title "Marl++" ls 3 dt (18,2,2,2), \
#     '../results/spf-tcp-natural-16' u 1:3 w lines smooth sbezier title "SPF" ls 5 dt (6,2,2,2), \
#     '../results/m-tcp-single-16' u 1:3 w lines smooth sbezier title "Marl++ (Single)" ls 6 dt (18,2), \
#     '../results/spf-tcp-single-16' u 1:3 w lines smooth sbezier title "SPF (Single)" ls 7 dt (6,2), \
#     '../results/tcp-combo-channel-16-avg.csv' u 1:3 w lines smooth sbezier title "MARL++ (Pretrain)" ls 6 dt (18,2), \
#     '../results/tcp-combo-16-avg.csv' u 1:3 w lines smooth sbezier title "MARL++ (Weird Pretrain)" ls 7 dt (6,2), \
