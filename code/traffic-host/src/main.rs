extern crate clap;
extern crate traffic_host;

use clap::{App, Arg, ArgMatches};
use std::{
	borrow::Cow,
	time::Duration,
};

static BYTES_IN_MEGABYTE: f64 = 1_048_576.0;
static BITS_IN_BYTE: f64 = 8.0;

fn parse_dl_rate(matches: &ArgMatches, param_name: &str) -> u64 {
	let val = matches.value_of(param_name)
		.unwrap_or_else(|| panic!("Must have a value for parameter {}.", param_name))
		.parse::<f64>()
		.unwrap_or_else(|_| panic!("Bandwidth value {} must be numeric.", param_name));

	match val {
		r if r > 0.0 => (BYTES_IN_MEGABYTE * r / BITS_IN_BYTE) as u64,
		_ => 0,
	}
}

fn main() {
	let matches =
		App::new("MARL Traffic Generator")
			.version("0.1.0")
			.author("Kyle Simpson <k.simpson.1@research.gla.ac.uk>")
			.about("Traffic generator (HTTP, others) for testing MARL.")
			.arg(Arg::with_name("server")
				.short("s")
				.long("server")
				.value_name("SERVER")
				.help("Server to send requests to.")
				.takes_value(true)
				.default_value("http://10.0.0.1"))
			.arg(Arg::with_name("wait")
				.short("w")
				.long("wait")
				.value_name("TIME_MS")
				.help("Amount of milliseconds to wait between requests.")
				.takes_value(true)
				.default_value("0"))
			.arg(Arg::with_name("count")
				.short("c")
				.long("count")
				.value_name("COUNT")
				.help("Amount of requests to make in total. 0 => Infinite.")
				.takes_value(true)
				.default_value("0"))
			.arg(Arg::with_name("http-dir")
				.short("d")
				.long("http-dir")
				.value_name("PATH")
				.help("Local directory tree to use as a basis for queries.")
				.takes_value(true)
				.default_value("htdocs"))
			.arg(Arg::with_name("bless")
				.short("b")
				.long("bless")
				.help("Regenerate file dependency lists, then exit."))
			.arg(Arg::with_name("random")
				.short("r")
				.long("random")
				.help("Request random files from the preset directory. Requires file dependency lists."))
			.arg(Arg::with_name("MAX_DOWN")
				.help("Maximum download rate from the target server (Mbps). If rate <= 0, then no limit is set.")
				.required_unless("bless")
				.index(1))
			.arg(Arg::with_name("MAX_UP")
				.help("Maximum upload rate to the target server (Mbps). Unlimited if unset or set to r <= 0.")
				.index(2)
				// .conflicts_with("bless")
				.default_value("-1"))
			.arg(Arg::with_name("dep-list")
				.short("l")
				.long("dep-list")
				.value_name("path")
				.help("Location to read/store file dependency information.")
				.takes_value(true)
				.default_value("./htdoc-deps.ron"))
			.get_matches();

	let url = Cow::from(
		matches.value_of_lossy("server")
			.expect("Server URL always guaranteed to exist...")
			.to_string()
	);
	
	let http_dir = Cow::from(
		matches.value_of_lossy("http-dir")
			.expect("Reference directory always guaranteed to exist...")
			.to_string()
	);

	let dep_list_dir = Cow::from(
		matches.value_of_lossy("dep-list")
			.expect("Dep-list directory always guaranteed to exist...")
			.to_string()
	);

	let requests = matches.value_of_lossy("count")
		.expect("Count always guaranteed to exist.")
		.parse::<u64>()
		.expect("Count MUST be an integer value.");

	let wait_ms = Duration::from_millis(
		matches.value_of_lossy("wait")
			.expect("Wait-time always guaranteed to exist.")
			.parse::<u64>()
			.expect("Wait-time MUST be an integer value.")
		);

	let requests = if requests == 0 {
		None
	} else {
		Some(requests)
	};

	let randomise = matches.is_present("random");

	if matches.is_present("bless") {
		println!("Bless mode!");

		let config = traffic_host::Config {
			dep_list_dir,
			http_dir,
			max_down: 0,
			max_up: 0,
			randomise,
			requests,
			url,
			wait_ms,
		};

		traffic_host::bless(config);
	} else {
		let max_down = parse_dl_rate(&matches, "MAX_DOWN");
		let max_up = parse_dl_rate(&matches, "MAX_UP");

		let config = traffic_host::Config {
			dep_list_dir,
			http_dir,
			max_down,
			max_up,
			randomise,
			requests,
			url,
			wait_ms,
		};

		traffic_host::run(config);
	}
}
