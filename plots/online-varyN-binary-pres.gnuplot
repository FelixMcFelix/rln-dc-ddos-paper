set terminal tikz standalone color size 9cm,6cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage[sfdefault]{FiraSans} \usepackage{newtxsf} \usepackage[T1]{fontenc} \renewcommand*\oldstylenums[1]{{\firaoldstyle #1}}\usepackage{siunitx}\sisetup{detect-all}'
set output "online-varyN-binary-pres.tex"

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

set xlabel "Iteration ($t \\cdot \\SI{50}{\\milli\\second}$)"
set ylabel "Ratio Legit Traffic Preserved"

set yrange [0.0:1.0]

plot '../results/online-2-avg.csv' u 1:3 w lines smooth sbezier title "$n=2$", \
     '../results/online-4-avg.csv' u 1:3 w lines smooth sbezier title "$n=4$", \
     '../results/online-8-avg.csv' u 1:3 w lines smooth sbezier title "$n=7$", \
     '../results/online-16-avg.csv' u 1:3 w lines smooth sbezier title "$n=11$"
