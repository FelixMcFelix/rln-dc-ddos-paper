set terminal tikz standalone color size 9cm,6cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage{times} \usepackage[T1]{fontenc} \usepackage{siunitx}\sisetup{detect-all}'
set output "ftprep-good-2.tex"

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
set key inside bottom right

plot '../results/baseline-2-avg.csv' u 1:3 w lines smooth sbezier title "baseline", \
     '../results/ft-f4-avg.csv' u 1:3 w lines smooth sbezier title "f4" ls 3, \
     '../results/ft-f5-avg.csv' u 1:3 w lines smooth sbezier title "f5" ls 5, \
     '../results/ft-f6-avg.csv' u 1:3 w lines smooth sbezier title "f6" ls 6, \
     '../results/ft-f7-avg.csv' u 1:3 w lines smooth sbezier title "f7" ls 7
