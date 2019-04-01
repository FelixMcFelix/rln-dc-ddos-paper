set terminal tikz standalone color size 9cm,6cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage{times} \usepackage[T1]{fontenc} \usepackage{siunitx}\sisetup{detect-all}'
set output "beast-validation.tex"

load "inferno.pal"

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

plot '../results/bmath-True.avg.csv' u 1:3 w lines smooth sbezier title "Single Agent, TCP, $n=16$ (Old Ubuntu, Beast 1)" dt 1, \
     '../results/beast-validation-Trueb1.avg.csv' u 1:3 w lines smooth sbezier title "Beast 1" ls 3 dt (18,2,2,2), \
     '../results/beast-validation-Trueb2.avg.csv' u 1:3 w lines smooth sbezier title "Beast 2" ls 5 dt (6,2,2,2), \
     #'../results/spf-tcp-single-16' u 1:3 w lines smooth sbezier title "SPF (Single)" ls 6 dt (18,2)