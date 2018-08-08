extern crate clap;
extern crate traffic_host;

use clap::{App, Arg, ArgMatches};
use std::borrow::Cow;

static BYTES_IN_MEGABYTE: f64 = 1_048_576.0;
static BITS_IN_BYTE: f64 = 8.0;

fn parse_dl_rate(matches: &ArgMatches, param_name: &str) -> u64 {
    let val = matches.value_of(param_name)
        .expect(&format!("Must have a value for parameter {}.", param_name))
        .parse::<f64>()
        .expect(&format!("Bandwidth value {} must be numeric.", param_name));

    match val {
        r if r > 0.0 => (BYTES_IN_MEGABYTE * r / BITS_IN_BYTE) as u64,
        _ => 0,
    }
}

fn main() {
    let matches =
        App::new("MARL Traffic Generator")
            .version("0.10")
            .author("Kyle Simpson <k.simpson.1@research.gla.ac.uk>")
            .about("Traffic generator (HTTP, others) for testing MARL.")
            .arg(Arg::with_name("server")
                 .short("s")
                 .long("server")
                 .value_name("SERVER")
                 .help("Server to send requests to.")
                 .takes_value(true)
                 .default_value("http://10.0.0.1"))
            .arg(Arg::with_name("http-dir")
                 .short("h")
                 .long("http-dir")
                 .value_name("PATH")
                 .help("Local directory tree to use as a basis for queries.")
                 .takes_value(true)
                 .default_value("htdocs"))
            .arg(Arg::with_name("MAX_DOWN")
                 .help("Maximum download rate from the target server (Mbps). If rate <= 0, then no limit is set.")
                 .required(true)
                 .index(1))
            .arg(Arg::with_name("MAX_UP")
                 .help("Maximum upload rate to the target server (Mbps). Unlimited if unset or set to r <= 0.")
                 .index(2)
                 .default_value("-1"))
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

    let max_down = parse_dl_rate(&matches, "MAX_DOWN");
    let max_up = parse_dl_rate(&matches, "MAX_UP");

    let config = traffic_host::Config {
        http_dir,
        max_down,
        max_up,
        url,
    };

    traffic_host::run(config);
}
