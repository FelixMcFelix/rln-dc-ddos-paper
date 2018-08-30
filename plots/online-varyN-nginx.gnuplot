set terminal tikz standalone color size 9cm,6cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage{times} \usepackage[T1]{fontenc} \usepackage{siunitx}\sisetup{detect-all}'
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

#set key autotitle columnhead
set datafile separator ","

set xlabel "Iteration ($t \\cdot{} \\SI{50}{\\milli\\second}$)"
set ylabel "Ratio Legit Traffic Preserved"

set yrange [0.0:1.0]

plot '../results/online-2-avg.csv' u 1:3 w lines smooth sbezier title "tcpreplay", \
	'../results/online-2-avg-ng.csv' u 1:3 w lines smooth sbezier title "nginx", \
	'../results/a-udp-avg.csv' u 1:3 w lines smooth sbezier title "hping3", \
	'../results/baseline-2-avg.csv' u 1:3 w lines smooth sbezier title "baseline-tcpreplay"
