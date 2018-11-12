set terminal tikz standalone color size 9cm,6cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage{times} \usepackage[T1]{fontenc} \usepackage{siunitx}\sisetup{detect-all}' createstyle
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
set xrange [-1.0:15.5]
set xtics ("Baseline" 0.0, \
	"4 $\\cdot{}$ Load" 1.0, \
	"IP" 2.0, \
	"Last Action" 3.0, \
	"Duration" 4.0, \
	"Baseline" 5.0, \
	"Correspondence Ratio" 6.0, \
	"Mean IAT" 7.0, \
	"$\\Delta$ In Rate" 8.0, \
	"$\\Delta$ Out Rate" 9.0, \
	"Packets In" 10.0, \
	"Packets Out" 11.0, \
	"Packets In Window" 12.0, \
	"Packets Out Window" 13.0, \
	"Mean In Packet Size" 14.0, \
	"Mean Out Packet Size" 15.0, \
	) scale 0.0
#set key inside bottom right
set boxwidth 1
unset key
set pointsize 0.1

plot '../results/baseline-2-avg-ng.csv' u (0.0):3:(1.0) ps .1, \
     '../results/ft-tcp-g-avg.csv' u (1.0):3:(1.0) ps .1, \
     '../results/ft-tcp-f0-avg.csv' u (2.0):3:(1.0) ps .1, \
     '../results/ft-tcp-f1-avg.csv' u (3.0):3:(1.0) ps .1, \
     '../results/ft-tcp-f2-avg.csv' u (4.0):3:(1.0) ps .1, \
     '../results/ft-tcp-f3-avg.csv' u (5.0):3:(1.0) ps .1, \
     '../results/ft-tcp-f4-avg.csv' u (6.0):3:(1.0) ps .1, \
     '../results/ft-tcp-f5-avg.csv' u (7.0):3:(1.0) ps .1, \
     '../results/ft-tcp-f6-avg.csv' u (8.0):3:(1.0) ps .1, \
     '../results/ft-tcp-f7-avg.csv' u (9.0):3:(1.0) ps .1, \
     '../results/ft-tcp-f8-avg.csv' u (10.0):3:(1.0) ps .1, \
     '../results/ft-tcp-f9-avg.csv' u (11.0):3:(1.0) ps .1, \
     '../results/ft-tcp-f10-avg.csv' u (12.0):3:(1.0) ps .1, \
     '../results/ft-tcp-f11-avg.csv' u (13.0):3:(1.0) ps .1, \
     '../results/ft-tcp-f12-avg.csv' u (14.0):3:(1.0) ps .1, \
     '../results/ft-tcp-f13-avg.csv' u (15.0):3:(1.0) ps .1 

set out
