set terminal tikz standalone color size 9cm,6cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage{times} \usepackage[T1]{fontenc} \usepackage{siunitx}\sisetup{detect-all}' createstyle
set output "tcp-box.tex"

#load "parula.pal"
load "inferno.pal"

set style line 102 lc rgb '#a0a0a0' lt 1 lw 1
set style boxplot outliers pointtype 7
set style data boxplot
set border ls 102
set colorbox border 102
set key textcolor rgb "black"
set tics textcolor rgb "black"
set label textcolor rgb "black"

set border 3
set grid y
set xtics nomirror
set xtics rotate by -45
set ytics nomirror

set key autotitle columnhead
set datafile separator ","

#set xlabel "Iteration ($t \\cdot{} \\SI{50}{\\milli\\second}$)"
set ylabel "Ratio Legit Traffic Preserved"

set yrange [0.0:1.0]
set xrange [-1.0:14.5]
set xtics ("Marl" 0.0, \
	"Marl++" 1.0, \
	"SPF" 2.0, \
	"Marl" 4.0, \
	"Marl++" 5.0, \
	"SPF" 6.0, \
	"Marl" 8.0, \
	"Marl++" 9.0, \
	"SPF" 10.0, \
	"Marl" 12.0, \
	"Marl++" 13.0, \
	"SPF" 14.0, \
	) scale 0.0
#set key inside bottom right
set boxwidth 1
unset key
set pointsize 0.1

set label "$n=2$" at graph 0.06,-0.22
set label "$n=4$" at graph 0.317,-0.22
set label "$n=8$" at graph 0.573,-0.22
set label "$n=16$" at graph 0.83,-0.22

plot '../results/online-2-avg-ng.csv' u (0.0):3:(1.0) ls 2 ps .1, \
     '../results/m-tcp-natural-2' u (1.0):3:(1.0) ls 2 ps .1, \
     '../results/spf-tcp-natural-2' u (2.0):3:(1.0) ls 2 ps .1, \
     '../results/online-4-avg-ng.csv' u (4.0):3:(1.0) ls 3 ps .1, \
     '../results/m-tcp-natural-4' u (5.0):3:(1.0) ls 3 ps .1, \
     '../results/spf-tcp-natural-4' u (6.0):3:(1.0) ls 3 ps .1, \
     '../results/online-8-avg-ng.csv' u (8.0):3:(1.0) ls 5 ps .1, \
     '../results/m-tcp-natural-8' u (9.0):3:(1.0) ls 5 ps .1, \
     '../results/spf-tcp-natural-8' u (10.0):3:(1.0) ls 5 ps .1, \
     '../results/online-16-avg-ng.csv' u (12.0):3:(1.0) ls 6 ps .1, \
     '../results/m-tcp-natural-16' u (13.0):3:(1.0) ls 6 ps .1, \
     '../results/spf-tcp-natural-16' u (14.0):3:(1.0) ls 6 ps .1, \

set out
