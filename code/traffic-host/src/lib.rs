extern crate curl;
extern crate parking_lot;
extern crate rayon;
extern crate ron;
extern crate select;
#[macro_use]
extern crate serde;
extern crate url;

use curl::easy::Easy as Easy;
use ron::ser::{
	self,
	PrettyConfig,
};
use std::{
	fs,
	io,
	sync::mpsc::{self, Receiver, TryRecvError},
	thread,
};

pub use config::Config;

mod config;
mod content;
mod walk;

pub fn bless(options: Config<'static>) {
	if let Ok(deps) = walk::walk(&options) {
		let out = ser::to_string_pretty(&deps, PrettyConfig::default())
			.expect("It should be valid!");

		fs::write(options.dep_list_dir.clone().into_owned(), &out[..])
			.expect("Should be able to write out dep-tree to a file...");
	}
}

pub fn run(options: Config<'static>) {
	curl::init();

	let mut buffer = String::new();
	let stdin = io::stdin();

	let (tx, rx) = mpsc::channel();

	// Here: listen for EOL (and then kill inner thread).
	// Inner thread does request loop.
	let handle = thread::spawn(move || request_loop(rx, options));
	stdin.read_line(&mut buffer);
	tx.send(CliCommand::End);

	handle.join();
}

enum CliCommand {
	End,
}

fn request_loop(rx: Receiver<CliCommand>, options: Config) {
	let mut easy = Easy::new();
	loop {
		match rx.try_recv() {
			Err(TryRecvError::Empty) => {
				// Make a request. It's our time!

				// May want to bind write function handlers, idk.
				// Also, bind to append the document needed I guess...
				easy.url(&options.url).unwrap();
				easy.max_send_speed(options.max_up).unwrap();
				easy.max_recv_speed(options.max_down).unwrap();

				match easy.perform() {
					Err(e) => {},//eprintln!("error making download: {:?}", e),
					_ => {},
				}
			}
			Ok(CliCommand::End) | Err(_) => {break;},
		}
	}
}
