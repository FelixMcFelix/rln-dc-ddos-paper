set terminal tikz standalone color size 9cm,6cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage{times} \usepackage[T1]{fontenc} \usepackage[binary-units, per-mode=symbol]{siunitx}\sisetup{detect-all}'
set output "ftprep-load.tex"

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
set ylabel "Total load (\\si{\\mega\\bit\\per\\second})"

plot '../results/ft-g-avg.csv' u 1:4 w lines smooth sbezier title "G", \
     '../results/ft-f0-avg.csv' u 1:4 w lines smooth sbezier title "f0", \
     '../results/ft-f1-avg.csv' u 1:4 w lines smooth sbezier title "f1", \
     '../results/ft-f2-avg.csv' u 1:4 w lines smooth sbezier title "f2", \
     '../results/ft-f3-avg.csv' u 1:4 w lines smooth sbezier title "f3", \
     '../results/ft-f4-avg.csv' u 1:4 w lines smooth sbezier title "f4", \
     '../results/ft-f5-avg.csv' u 1:4 w lines smooth sbezier title "f5", \
     '../results/ft-f6-avg.csv' u 1:4 w lines smooth sbezier title "f6", \
     '../results/ft-f7-avg.csv' u 1:4 w lines smooth sbezier title "f7"
