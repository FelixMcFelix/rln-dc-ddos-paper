#[macro_use]
extern crate log;

mod config;
mod trace;

pub use config::Config;

use byteorder::{
	NetworkEndian,
	ReadBytesExt,
	WriteBytesExt,
};
use net2::{
	unix::UnixUdpBuilderExt,
	UdpBuilder,
};
use rand::{
	distributions::{
		Uniform,
	},
	prelude::*,
};
use std::{
	collections::HashMap,
	io::{
		Read,
		Result as IoResult,
	},
	net::{
		UdpSocket,
		SocketAddr,
	},
	thread,
	time::{
		Duration,
		Instant,
	},
};
use trace::*;

fn make_udp_socket(port: u16, non_block: bool) -> IoResult<UdpSocket> {
	let out = UdpBuilder::new_v4()?;
	
	out.reuse_address(true)?;

	if !cfg!(windows) {
		out.reuse_port(true)?;
	}

	let out = out.bind(("127.0.0.1", port))?;
	out.set_nonblocking(non_block)?;

	Ok(out)
}

pub fn client(config: Config) {
	let ts = trace::read_traces();

	crossbeam::scope(|s| {
		for i in 0..config.thread_count {
			s.spawn(|_| {
				inner_client(&config, &ts);
			});
		}
	}).unwrap();
}

const CMAC_BYTES: usize = 16;
const RTP_BYTES: usize = 12;

fn inner_client(config: &Config, ts: &Vec<Trace>) {
	let mut rng = thread_rng();

	let draw = Uniform::new(0, ts.len());

	let port_distrib = Uniform::new(30000, 54000);
	let port = port_distrib.sample(&mut rng);

	let end = if config.randomise_duration {
		let time_distrib = Uniform::new(
			config.duration_lb,
			config.duration_ub
				.expect("No upper bound set: cannot randomise call time."),
		);
		let port = time_distrib.sample(&mut rng);
	} else {
		config.duration_ub;
	};

	let el = &ts[draw.sample(&mut rng)];
	
	let socket = make_udp_socket(port, true).unwrap();

	println!("Listening on port {:?}", port);

	let mut buf = [0u8; 1560];
	let mut rxbuf = [0u8; 1560];
	let ssrc = rng.gen::<u32>();
	(&mut buf[8..12]).write_u32::<NetworkEndian>(ssrc);

	let start = Instant::now();
	let mut last_size = None;
	for pkt in el {
		use PacketChainLink::*;
		let mut sleep_time = 20 + match pkt {
			Packet(p) => {
				let p = usize::from(p.get());
				last_size = Some(p);
				println!("Sending packet of size {:?} (before CMAC, RTP, ... )", p);
				socket.send_to(&buf[..p + CMAC_BYTES + RTP_BYTES], &config.address);
				0
			},
			Missing(t) => {
				if let Some(p) = last_size {
					println!("Sending packet of size {:?} (before CMAC, RTP, ... )", p);
					socket.send_to(&buf[..p + CMAC_BYTES + RTP_BYTES], &config.address);
				}
				0
			},
			Silence(t) => {
				println!("Waiting for {:?}ms.", t);
				// Note: won't receive packets in here...
				let out = u64::from(*t);
				out.min(config.max_silence.unwrap_or(out))
			}
		};

		while sleep_time > 0 {
			thread::sleep(Duration::from_millis(sleep_time.min(20)));
			sleep_time -= 20;
		}

		while let Ok((sz, addr)) = socket.recv_from(&mut rxbuf) {
			println!("Received {:?} bytes from {:?}", sz, addr);
		}
	}
}

pub fn server (config: Config) {
	// Okay, figure out what I want to do.
	// Simplification for now: cache IPs and ssrcs
	// (src picks randomly).
	// Just run it as one room, which everyone joins.
	// FIXME: assign SSRC and send out-of-band.
	// FIXME: assign clients to rooms so that it's not a massive 256-man call?
	let socket = make_udp_socket(config.port, false).unwrap();

	let mut ip_map: HashMap<u32, SocketAddr> = Default::default();
	let mut buf = [0u8; 1560];

	loop {
		if let Ok((sz, addr)) = socket.recv_from(&mut buf) {
			println!("Packet!");
			let ssrc = (&buf[8..12]).read_u32::<NetworkEndian>().unwrap();

			let _ = ip_map.insert(ssrc, addr);

			for (o_ssrc, o_addr) in ip_map.iter() {
				if *o_ssrc != ssrc {
					socket.send_to(&buf[..sz], o_addr);
					println!("Sent {} bytes to {:?}", sz, o_addr);
				}
			}
		}
	}
}