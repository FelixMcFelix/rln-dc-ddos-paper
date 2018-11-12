set terminal tikz standalone color size 10cm,6.67cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage{times} \usepackage[T1]{fontenc} \usepackage{siunitx}\sisetup{detect-all}' createstyle
set output "policy-16-tcp-f5-sum.tex"

#load "parula.pal"
load "inferno.pal"

set style line 102 lc rgb '#a0a0a0' lt 1 lw 1
#set style boxplot outliers pointtype 7
#set style data boxplot
set border ls 102
set colorbox border 102
set key textcolor rgb "black"
set tics textcolor rgb "black"
set label textcolor rgb "black"

set border 3
#set grid y
set xtics nomirror
#set xtics rotate by -45
set ytics nomirror

#set key autotitle columnhead
set datafile separator ","

#set xlabel "Iteration ($t \\cdot{} \\SI{50}{\\milli\\second}$)"
#set ylabel "Ratio Legit Traffic Preserved"

#set yrange [0.0:1.0]
#set xrange [-1.0:23.0]
#set key inside bottom right

plot '../results/tcp-action-f5-16-sum-p.csv' matrix rowheaders columnheaders u 1:2:3 with image pixels

set out
