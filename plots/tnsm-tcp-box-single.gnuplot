set terminal tikz standalone color size 9cm,6cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage{times} \usepackage[T1]{fontenc} \usepackage{siunitx}\sisetup{detect-all}' createstyle
set output "tnsm-tcp-box-single.tex"

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
	"SPF " 14.0, \
	) scale 0.0
#set key inside bottom right
set boxwidth 1
unset key
set pointsize 0.1

set label "$n=2$" at graph 0.06,-0.22
set label "$n=4$" at graph 0.317,-0.22
set label "$n=8$" at graph 0.573,-0.22
set label "$n=16$" at graph 0.83,-0.22

plot '../results/tnsm-tree-2-tcp-m-separate.avg.csv' u (0.0):3:(1.0) ls 1 ps .1, \
     '../results/tnsm-tree-2-tcp-mpp-single.avg.csv' u (1.0):3:(1.0) ls 1 ps .1, \
     '../results/tnsm-tree-2-tcp-spf-single.avg.csv' u (2.0):3:(1.0) ls 1 ps .1, \
     '../results/tnsm-tree-4-tcp-m-separate.avg.csv' u (4.0):3:(1.0) ls 3 ps .1, \
     '../results/tnsm-tree-4-tcp-mpp-single.avg.csv' u (5.0):3:(1.0) ls 3 ps .1, \
     '../results/tnsm-tree-4-tcp-spf-single.avg.csv' u (6.0):3:(1.0) ls 3 ps .1, \
     '../results/tnsm-tree-8-tcp-m-separate.avg.csv' u (8.0):3:(1.0) ls 5 ps .1, \
     '../results/tnsm-tree-8-tcp-mpp-single.avg.csv' u (9.0):3:(1.0) ls 5 ps .1, \
     '../results/tnsm-tree-8-tcp-spf-single.avg.csv' u (10.0):3:(1.0) ls 5 ps .1, \
     '../results/tnsm-tree-16-tcp-m-separate.avg.csv' u (12.0):3:(1.0) ls 7 ps .1, \
     '../results/tnsm-tree-16-tcp-mpp-single.avg.csv' u (13.0):3:(1.0) ls 7 ps .1, \
     '../results/tnsm-tree-16-tcp-spf-single.avg.csv' u (14.0):3:(1.0) ls 7 ps .1, \

set out
