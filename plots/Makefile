source_data := $(wildcard ../results/*.csv)
targets := $(patsubst %.gnuplot,%.pdf,$(wildcard *.gnuplot))

marker: $(targets)
	touch marker

%.pdf: %.tex
	latexmk -lualatex -pdf $< > /dev/null 2>&1

%.tex: %.gnuplot $(source_data)
	gnuplot -e "load 'config/preamble.cfg'" $<

