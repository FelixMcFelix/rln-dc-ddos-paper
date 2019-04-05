mod packet_format;

use rayon::prelude::*;
use std::{
	fmt::Debug,
	fs::{
		self,
		File,
	},
	path::PathBuf,
};

pub(crate) use packet_format::*;

const TRACE_DIR: &str = "traces/";

pub type Trace = Vec<PacketChainLink>;

pub fn read_traces(base_dir: &String) -> Vec<Trace> {
	let file_entries: Vec<PathBuf> = fs::read_dir(&format!("{}/{}", base_dir, TRACE_DIR))
		.expect("Couldn't read files in trace directory...")
		.filter_map(|x| if let Ok(x) = x {
			Some(x.path())
		} else {
			warn!("Couldn't read entry: {:?}", x);
			None
		}).collect();

	file_entries.par_iter()
		.map(File::open)
		.filter_map(warn_and_unpack)
		.map(bincode::deserialize_from)
		.filter_map(warn_and_unpack)
		.filter(|x: &Trace| !x.is_empty())
		.collect()
}

fn warn_and_unpack<T, E: Debug>(input: Result<T, E>) -> Option<T> {
	input.map_err(|why| {
		warn!("Couldn't parse entry: {:?}", why);
		why
	}).ok()
}
