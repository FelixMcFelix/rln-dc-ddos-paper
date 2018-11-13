set terminal tikz standalone color size 9cm,6cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage{times} \usepackage[T1]{fontenc} \usepackage{siunitx}\sisetup{detect-all}' createstyle
set output "policy-4-tcp-f5-mean.tex"

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
set grid y
set xtics nomirror
set xtics offset 1.5,0
set xtics (0, 1, 2, 3, 4, 5, 6, 7, 8, 9)
set ytics nomirror

set datafile separator ","

set xlabel "Action"
set ylabel "Mean IAT ($\\si{\milli\second}$)"
set label "Value" at graph 0.98,1.05

set yrange [0.0:10000.0]
set xrange [0.0:10.0]
#set key inside bottom right

#set lmargin at screen 0.05;
#set rmargin at screen 1.1;
#set bmargin at screen 0.1;
#set tmargin at screen 0.95;

#set log cb

xs(x) = x - .5
ys(y) = y * (10000.0 / 50.0)

plot '../results/tcp-action-f5-4-mean-p.csv' matrix u (xs($1)):(ys($2)):3 every ::1 with image pixels notitle

set out
