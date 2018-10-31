set terminal tikz standalone color size 10.5cm,7cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage{times} \usepackage[T1]{fontenc} \usepackage{siunitx}\sisetup{detect-all}'
set output "online-varyN-nginx.tex"

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
#set key above

#set key autotitle columnhead
set datafile separator ","

set xlabel "Iteration ($t \\cdot{} \\SI{50}{\\milli\\second}$)"
set ylabel "Ratio Legit Traffic Preserved"

set yrange [0.0:1.0]

#'../results/online-2-avg-ng.csv' u 1:3 w lines smooth sbezier title "nginx", \

plot '../results/online-2-avg.csv' u 1:3 w lines smooth sbezier title "tcpreplay" ls 1 dt (18,2,2,2), \
	'../results/ft-tcp-g-avg.csv' u 1:3 w lines smooth sbezier title "nginx" ls 3 dt (6,2,2,2), \
	'../results/a-udp-avg.csv' u 1:3 w lines smooth sbezier title "hping3" ls 4 dt (6,2), \
	'../results/baseline-2-avg.csv' u 1:3 w lines smooth sbezier title "baseline-tcpreplay" ls 5 dt (18,2), \
	'../results/baseline-2-avg-ng.csv' u 1:3 w lines smooth sbezier title "baseline-nginx" ls 7 dt 1
