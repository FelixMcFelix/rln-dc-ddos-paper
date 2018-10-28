set terminal tikz standalone color size 9cm,6cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage{times} \usepackage[T1]{fontenc} \usepackage[binary-units, per-mode=symbol]{siunitx}\sisetup{detect-all}'
set output "ftprep-tcp-combine-load.tex"

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

set xrange [0.0:3000.0]

plot '../results/ft-tcp-g-avg.csv' u 1:4 w lines smooth sbezier title "G", \
     '../results/ft-tcp-combine-f0-avg.csv' u 1:4 w lines smooth sbezier title "cf0", \
     '../results/ft-tcp-combine-f1-avg.csv' u 1:4 w lines smooth sbezier title "cf1", \
     '../results/ft-tcp-combine-f2-avg.csv' u 1:4 w lines smooth sbezier title "cf2", \
     '../results/ft-tcp-combine-f3-avg.csv' u 1:4 w lines smooth sbezier title "cf3", \
     '../results/ft-tcp-combine-f4-avg.csv' u 1:4 w lines smooth sbezier title "cf4", \
     '../results/ft-tcp-combine-f5-avg.csv' u 1:4 w lines smooth sbezier title "cf5", \
     '../results/ft-tcp-combine-f6-avg.csv' u 1:4 w lines smooth sbezier title "cf6", \
     '../results/ft-tcp-combine-f7-avg.csv' u 1:4 w lines smooth sbezier title "cf7"
