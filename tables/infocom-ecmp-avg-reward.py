import csv
import numpy as np
from os import path
import sys

traffics = ["opus", "tcp"]
ns = [2, 4, 8, 16]
models = ["mpp", "spf"]
variants = [
	("separate", None, "Separate", None),
	("single", None, "Single", None),
]

illegal_combos = set()
#illegal_combos.add(("spf", "opus", "single"))
# illegal_combos.add(("spf", "udp", "channel"))
# illegal_combos.add(("spf", "tcp", "channel"))

def get_average_reward(filename):
	output = 0.0
	try:
		with open(filename, "r") as csvfile:
			reader = csv.reader(csvfile)
			# _ = nereader.next()

			dats = []
			for i, row in enumerate(reader):
				if i == 0:
					continue

				dats.append(float(row[3]))

			output = np.mean(dats)
	except:
		print("file {} not found".format(filename))
	return output

def write_table(out_file, data):
	lm = len(models)
	lv = len(variants)

	out_file.write(
		"\\begin{{tabular}}{{@{{}}cc{}@{{}}}}\n".format("S"*((lm*lv)+2))
	)
	out_file.write(
		"\\toprule\\multicolumn{1}{c}{Traffic} & " + \
		"\\multicolumn{1}{c}{$n$} & " + \
		"\\multicolumn{1}{c}{Unprotected} & " + \
		"\\multicolumn{1}{c}{Marl} & " + \
		"\\multicolumn{{{}}}{{c}}{{Instant}} & ".format(lv) + \
		"\\multicolumn{{{}}}{{c}}{{Guarded}} ".format(lv) + \
		"\\\\\n" + \
		"\\cmidrule(lr){{5-{}}}\\cmidrule(lr){{{}-{}}} ".format(5 + lv-1, 5 + lv, 4 + lv + lv) + \
		" & & & "
	)

	for _ in models:
		for (_fn, _replace_str, pres, _replace_m) in variants:
			out_file.write("& \\multicolumn{{1}}{{c}}{{{}}} ".format(pres))

	out_file.write("\\\\ \\midrule\n")

	# Write file body.
	for traffic in traffics:
		for i, n in enumerate(ns):
			key = (traffic,n)
			out_file.write("{} & {} ".format("" if i>0 else traffic.upper(), n * 3))

			row = data[key]
			for j, _ in enumerate(row):
				if j == 0:
					continue

				j -= 2
				# print(j, len(variants))
				# print(j, models, len(models), len(variants))
				model = models[int(j/len(variants))]
				variant = variants[j%len(variants)][0]
				if (model, traffic, variant) in illegal_combos:
					row[j+1] = -1000.0

			to_bold = np.argmax(row)

			for j, val in enumerate(row):
				base = "& {:.3f} " if j != to_bold else "& \\bfseries {:.3f} "

				if val < -999.0:
					base = "& \\multicolumn{{1}}{{c}}{{---}} "					

				out_file.write(base.format(val))

			out_file.write("\\\\ \n")

	out_file.write("\\bottomrule\n\\end{tabular}")

def get_data():
	data = {}
	for t_i, t in enumerate(traffics):
		for n in ns:
			key = (t, n)
			row = []

			row.append(get_average_reward(
				"../results/tnsm-baseline-ecmp-{}-{}.csv".format(
					n,
					t,
					)
				))

			row.append(get_average_reward(
				"../results/tnsm-ecmp-{}-{}-m-separate.csv".format(
					n,
					t,
					)
				))

			# do it for all parts now.
			for m_i, m in enumerate(models):
				for v in variants:
					f_str = "../results/tnsm-ecmp-{}-{}-{}-{}.csv" if v[1] is None else v[1]
					m_str = m if v[3] is None else v[3][m_i]
					row.append(get_average_reward(
						# f_str.format(m_str, t, v[0], n)
						f_str.format(n, t, m, v[0])
					))

			data[key] = np.array(row)

	return data

def main():
	(_dir, script_name) = path.split(sys.argv[0])
	out_name = path.splitext(script_name)[0] + ".tex"

	data = get_data()

	with open(out_name, "w") as outf:
		write_table(outf, data)

if __name__ == '__main__':
	main()
