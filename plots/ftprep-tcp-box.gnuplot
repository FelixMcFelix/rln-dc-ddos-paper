set terminal tikz standalone color size 10cm,6.67cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage{times} \usepackage[T1]{fontenc} \usepackage{siunitx}\sisetup{detect-all}' createstyle
set output "ftprep-tcp-box.tex"

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
set xrange [-1.0:23.0]
set xtics ("Baseline" 0.0, \
	"Global" 1.5, \
	"IP" 3.0, \
	"Last Action" 4.5, \
	"Duration" 6.0, \
	"Baseline" 7.5, \
	"$C_X$" 9.0, \
	"Mean IAT" 10.5, \
	"$\\Delta$ In Rate" 12.0, \
	"$\\Delta$ Out Rate" 13.5, \
	"Packets In" 15.0, \
	"Packets Out" 16.5, \
	"InPkts (Window)" 18.0, \
	"OutPkts (Window)" 19.5, \
	"Mean InPkt Size" 21.0, \
	"Mean OutPkt Size" 22.5, \
	) scale 0.0
#set key inside bottom right
set boxwidth 1
unset key
set pointsize 0.1

stats '../results/baseline-2-avg-ng.csv' u 3
set arrow from -1.0,STATS_up_quartile to 23.0,STATS_up_quartile nohead ls 1 dt "." lc rgb '#a7000004' 
set arrow from -1.0,STATS_lo_quartile to 23.0,STATS_lo_quartile nohead ls 1 dt "." lc rgb '#a7000004' 

plot '../results/baseline-2-avg-ng.csv' u (0.0):3:(1.0) ls 1 ps .1, \
     '../results/ft-tcp-g-avg.csv' u (1.5):3:(1.0) ls 2 ps .1, \
     '../results/ft-tcp-f0-avg.csv' u (3.0):3:(1.0) ls 3 ps .1, \
     '../results/ft-tcp-f1-avg.csv' u (4.5):3:(1.0) ls 4 ps .1, \
     '../results/ft-tcp-f2-avg.csv' u (6.0):3:(1.0) ls 5 ps .1, \
     '../results/ft-tcp-f3-avg.csv' u (7.5):3:(1.0) ls 6 ps .1, \
     '../results/ft-tcp-f4-avg.csv' u (9.0):3:(1.0) ls 7 ps .1, \
     '../results/ft-tcp-f5-avg.csv' u (10.5):3:(1.0) ls 8 ps .1, \
     '../results/ft-tcp-f6-avg.csv' u (12.0):3:(1.0) ls 2 ps .1, \
     '../results/ft-tcp-f7-avg.csv' u (13.5):3:(1.0) ls 3 ps .1, \
     '../results/ft-tcp-f8-avg.csv' u (15.0):3:(1.0) ls 4 ps .1, \
     '../results/ft-tcp-f9-avg.csv' u (16.5):3:(1.0) ls 5 ps .1, \
     '../results/ft-tcp-f10-avg.csv' u (18.0):3:(1.0) ls 6 ps .1, \
     '../results/ft-tcp-f11-avg.csv' u (19.5):3:(1.0) ls 7 ps .1, \
     '../results/ft-tcp-f12-avg.csv' u (21.0):3:(1.0) ls 8 ps .1, \
     '../results/ft-tcp-f13-avg.csv' u (22.5):3:(1.0) ls 2 ps .1

set out
