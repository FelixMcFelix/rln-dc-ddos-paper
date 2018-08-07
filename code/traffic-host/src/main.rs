extern crate clap;
extern crate traffic_host;

use clap::{Arg, App};

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
                 .default_value("10.0.0.1"))
            .arg(Arg::with_name("http-dir")
                 .short("h")
                 .long("http-dir")
                 .value_name("PATH")
                 .help("Local directory tree to use as a basis for queries.")
                 .takes_value(true)
                 .default_value("htdocs"))
            .arg(Arg::with_name("MAX_DOWN")
                 .help("Maximum download rate from the target server.")
                 .required(true)
                 .index(1))
            .arg(Arg::with_name("MAX_UP")
                 .help("Maximum upload rate to the target server.")
                 .index(2))
            .get_matches();

    // e.g., (before conversion to a real URL/address for library use)
    let _url = matches.value_of("server")
        .expect("Server URL always guaranteed to exist...");

    let config = traffic_host::Config {

    };

    traffic_host::run(config);
}
