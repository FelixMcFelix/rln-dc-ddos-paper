set terminal tikz standalone color size 9cm,6cm font '\scriptsize' preamble '\usepackage{microtype}'
set output "offline-reward.tex"

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

set xlabel "Episode"
set ylabel "Global Reward"

plot '../results/offline-avg.csv' u 1:2 w lines smooth sbezier title "Last $t$", \
     '../results/offline-avg.csv' u 1:5 w lines smooth sbezier title "Average"
