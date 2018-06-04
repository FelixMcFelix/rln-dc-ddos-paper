set terminal tikz standalone color size 9cm,6cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage{times} \usepackage[binary-units]{siunitx}'
set output "online-cond-prot.tex"

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
set ylabel "Average Total Load (\\si{\\mega\\bit\\per\\second})"

# set yrange [-1.0:1.0]

plot '../results/online-avg.csv' u 1:4 every ::::1000 w lines smooth sbezier title "Enforced", \
     '../results/online-noprot-avg.csv' u 1:4 every ::::1000 w lines smooth sbezier title "Not-so-enforced"

set ylabel "Average Global Reward"

set output "online-cond-prot-reward.tex"
plot '../results/online-avg.csv' u 1:2 w lines smooth sbezier title "Enforced", \
     '../results/online-noprot-avg.csv' u 1:2 w lines smooth sbezier title "Not-so-enforced"

set ylabel "Ratio Legit Traffic Preserved"

set output "online-cond-prot-good.tex"
plot '../results/online-avg.csv' u 1:3 w lines smooth sbezier title "Enforced", \
     '../results/online-noprot-avg.csv' u 1:3 w lines smooth sbezier title "Not-so-enforced"