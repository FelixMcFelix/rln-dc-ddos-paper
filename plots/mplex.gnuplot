set terminal tikz standalone color size 9cm,6cm font '\scriptsize' preamble '\usepackage{microtype} \usepackage{times} \usepackage[binary-units]{siunitx}'
set output "mplex.tex"

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

set xlabel "Time (s)"
set ylabel "Upload rate (\\si{\\mega\\bit\\per\\second})"

set xrange [0:30]

# c1s = system("awk -F ',' '{if ($1==\"1.0\" || $1==\"5.0\"){ print $1 }}' ../results/mplex-tcp.csv | sort | uniq")
c1s = system("awk -F ',' '{ print $1 }' ../results/mplex-tcp.csv | sort | uniq")

plot for [c1 in c1s] sprintf('< grep ''\b%s\b'' ../results/mplex-tcp.csv', c1) using 2:3 every ::::29 w lines title c1