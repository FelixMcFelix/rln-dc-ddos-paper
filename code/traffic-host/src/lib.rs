extern crate curl;

mod config;

use curl::easy::Easy as Easy;
use std::{
    io,
    sync::mpsc::{self, Receiver, TryRecvError},
    thread,
};

pub use config::Config;

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

                easy.perform();
            }
            Ok(CliCommand::End) | Err(_) => {break;},
        }
    }
}
