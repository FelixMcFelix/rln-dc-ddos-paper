import csv
import numpy as np
from os import path
import sys

traffics = ["udp", "tcp"]
ns = [2, 4, 8, 16]
models = ["m", "spf"]
variants = [
	("natural", "Capped"),
	("uncap", "Uncapped"),
	("banded", "Banded"),
	("single", "Single"),
]

def get_average_reward(filename):
	with open(filename, "rb") as csvfile:
		reader = csv.reader(csvfile)
		_ = reader.next()

		dats = []
		for row in reader:
			dats.append(float(row[3]))

		return np.mean(dats)

def write_table(out_file, data):
	lm = len(models)
	lv = len(variants)

	out_file.write(
		"\\begin{{tabular}}{{@{{}}lc{}@{{}}}}\n".format("S"*((lm*lv)+1))
	)
	out_file.write(
		"\\toprule\\multicolumn{1}{c}{Traffic} & " + \
		"\\multicolumn{1}{c}{$n$} & " + \
		"\\multicolumn{1}{c}{Marl} & " + \
		"\\multicolumn{{{}}}{{c}}{{Marl++}} & ".format(lv) + \
		"\\multicolumn{{{}}}{{c}}{{SPF}} ".format(lv) + \
		"\\cmidrule(lr){{4-{}}}\\cmidrule(lr){{{}-{}}} \\\\\n".format(4 + lv-1, 4 + lv, 3 + lv + lv) + \
		" & & "
	)

	for _ in models:
		for (_fn, pres) in variants:
			out_file.write("& \\multicolumn{{1}}{{c}}{{{}}} ".format(pres))

	out_file.write("\\\\ \\midrule\n")

	# Write file body.
	for traffic in traffics:
		for i, n in enumerate(ns):
			key = (traffic,n)
			out_file.write("{} & {} ".format("" if i>0 else traffic.upper(), n))

			row = data[key]
			to_bold = np.argmax(row)
			for j, val in enumerate(row):
				base = "& {} " if j != to_bold else "& \\textbf{{{}}} "
				out_file.write(base.format(val))

			out_file.write("\\\\ \n")

	out_file.write("\\bottomrule\n\\end{{tabular}}")

def get_data():
	data = {}
	for t in traffics:
		for n in ns:
			key = (t, n)
			row = []

			row.append(get_average_reward(
				"../results/online-{}{}.csv".format(
					n,
					"" if t == "udp" else "-ng"
					)
				))

			# do it for all parts now.
			for m in models:
				for v in variants:
					row.append(get_average_reward(
						"../results/{}-{}-{}-{}.csv".format(m, t, v[0], n)
					))

			data[key] = np.array(row)

	return data

def main():
	(_dir, script_name) = path.split(sys.argv[0])
	out_name = path.splitext(script_name)[0] + ".tex"

	data = get_data()
	print data

	with open(out_name, "w") as outf:
		write_table(outf, data)

if __name__ == '__main__':
	main()