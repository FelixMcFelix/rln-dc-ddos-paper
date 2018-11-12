set terminal tikz standalone color size 9cm,6cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage{times} \usepackage[T1]{fontenc} \usepackage{siunitx}\sisetup{detect-all}' createstyle
set output "ftprep-tcp-cap-box.tex"

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
	"4 $\\cdot{}$ Load" 1.1, \
	"IP" 2.2, \
	"Last Action" 3.3, \
	"Duration" 4.4, \
	"Baseline" 5.5, \
	"Correspondence Ratio" 6.6, \
	"Mean IAT" 7.7, \
	"$\\Delta$ In Rate" 8.8, \
	"$\\Delta$ Out Rate" 9.9, \
	"Packets In" 11.0, \
	"Packets Out" 12.1, \
	"Packets In Window" 13.2, \
	"Packets Out Window" 14.3, \
	"Mean In Packet Size" 15.4, \
	"Mean Out Packet Size" 16.5, \
	) scale 0.0
#set key inside bottom right
set boxwidth 1
unset key
set pointsize 0.1

plot '../results/baseline-2-avg-ng.csv' u (0.0):3:(1.0) ps .1, \
     '../results/ft-tcp-cap-g-avg.csv' u (1.1):3:(1.0) ls 2 ps .1, \
     '../results/ft-tcp-cap-f0-avg.csv' u (2.2):3:(1.0) ls 3 ps .1, \
     '../results/ft-tcp-cap-f1-avg.csv' u (3.3):3:(1.0) ls 4 ps .1, \
     '../results/ft-tcp-cap-f2-avg.csv' u (4.4):3:(1.0) ls 5 ps .1, \
     '../results/ft-tcp-cap-f3-avg.csv' u (5.5):3:(1.0) ls 6 ps .1, \
     '../results/ft-tcp-cap-f4-avg.csv' u (6.6):3:(1.0) ls 7 ps .1, \
     '../results/ft-tcp-cap-f5-avg.csv' u (7.7):3:(1.0) ls 8 ps .1, \
     '../results/ft-tcp-cap-f6-avg.csv' u (8.8):3:(1.0) ls 2 ps .1, \
     '../results/ft-tcp-cap-f7-avg.csv' u (9.9):3:(1.0) ls 3 ps .1, \
     '../results/ft-tcp-cap-f8-avg.csv' u (11.0):3:(1.0) ls 4 ps .1, \
     '../results/ft-tcp-cap-f9-avg.csv' u (12.1):3:(1.0) ls 5 ps .1, \
     '../results/ft-tcp-cap-f10-avg.csv' u (13.2):3:(1.0) ls 6 ps .1, \
     '../results/ft-tcp-cap-f11-avg.csv' u (14.3):3:(1.0) ls 7 ps .1, \
     '../results/ft-tcp-cap-f12-avg.csv' u (15.4):3:(1.0) ls 8 ps .1, \
     '../results/ft-tcp-cap-f13-avg.csv' u (16.5):3:(1.0) ls 2 ps .1 

set out
