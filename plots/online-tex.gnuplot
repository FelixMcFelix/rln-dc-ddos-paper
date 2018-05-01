set terminal tikz standalone color size 9cm,6cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage{times}'
set output "online.tex"

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

set xlabel "Iteration (t * 50ms)"
set ylabel "Ratio Legit Traffic Preserved"

plot '../results/online-standard-avg.csv' u 1:3 w lines smooth sbezier title "$n=2$", \
     '../results/online-mod-avg.csv' u 1:3 w lines smooth sbezier title "$n=7$", \
     '../results/online-mod-more-avg.csv' u 1:3 w lines smooth sbezier title "$n=14$"
