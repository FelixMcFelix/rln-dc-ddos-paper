set terminal tikz standalone color size 9cm,6cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage{times} \usepackage[binary-units]{siunitx}'
set output "online-scale-load.tex"

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
set ylabel "Load (\\si{\\mega\\bit\\per\\second})"

us(x) = 62

plot us(x) w dots title "Max capacity", \
     '../results/online-scale-avg.csv' u 1:4 w lines smooth sbezier title "Scaled Max", \
     '../results/online-avg-uneven.csv' u 1:4 w lines smooth sbezier title "Verbatim Max"

