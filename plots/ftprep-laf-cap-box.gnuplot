set terminal tikz standalone color size 10cm,6.67cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage{times} \usepackage[T1]{fontenc} \usepackage{siunitx}\sisetup{detect-all}' createstyle
set output "ftprep-laf-cap-box.tex"

load "parula.pal"
#load "inferno.pal"

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
	"Duration" 4.5, \
	"Flow Size" 6.0, \
	"$C_X$" 7.5, \
	"Mean IAT" 9.0, \
	"$\\Delta$ In Rate" 10.5, \
	"$\\Delta$ Out Rate" 12.0, \
     "Packets In" 13.5, \
	"Packets Out" 15.0, \
	"InPkts (Window)" 16.5, \
	"OutPkts (Window)" 18.0, \
	"Mean InPkt Size" 19.5, \
	"Mean OutPkt Size" 21.0, \
     ) scale 0.0
	
#set key inside bottom right
set boxwidth 1
unset key
set pointsize 0.1

stats '../results/baseline-2-avg.csv' u 3
set arrow from -1.0,STATS_up_quartile to 23.0,STATS_up_quartile nohead ls 1 dt "." lc rgb '#a7352a87'
set arrow from -1.0,STATS_lo_quartile to 23.0,STATS_lo_quartile nohead ls 1 dt "." lc rgb '#a7352a87'

plot '../results/baseline-2-avg.csv' u (0.0):3:(1.0) ls 1, \
     '../results/ft-g-avg.csv' u (1.5):3:(1.0) ls 2, \
     '../results/ft-cap-laf,0-avg.csv' u (3.0):3:(1.0) ls 3, \
     '../results/ft-cap-laf,2-avg.csv' u (4.5):3:(1.0) ls 4, \
     '../results/ft-cap-laf,3-avg.csv' u (6.0):3:(1.0) ls 5, \
     '../results/ft-cap-laf,4-avg.csv' u (7.5):3:(1.0) ls 6, \
     '../results/ft-cap-laf,5-avg.csv' u (9.0):3:(1.0) ls 7, \
     '../results/ft-cap-laf,6-avg.csv' u (10.5):3:(1.0) ls 8, \
     '../results/ft-cap-laf,7-avg.csv' u (12.0):3:(1.0) ls 2, \
     '../results/ft-cap-laf,8-avg.csv' u (13.5):3:(1.0) ls 3, \
     '../results/ft-cap-laf,9-avg.csv' u (15.0):3:(1.0) ls 4, \
     '../results/ft-cap-laf,10-avg.csv' u (16.5):3:(1.0) ls 5, \
     '../results/ft-cap-laf,11-avg.csv' u (18.0):3:(1.0) ls 6, \
     '../results/ft-cap-laf,12-avg.csv' u (19.5):3:(1.0) ls 7, \
     '../results/ft-cap-laf,13-avg.csv' u (21.0):3:(1.0) ls 8

set out
