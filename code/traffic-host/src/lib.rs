extern crate cssparser;
extern crate curl;
extern crate parking_lot;
extern crate rand;
extern crate rayon;
extern crate ron;
extern crate select;
#[macro_use]
extern crate serde;
extern crate url;

use content::{
	Dependencies,
	DependencyList,
	FileDesc,
	FileType,
};
use curl::easy::Easy as Easy;
use rand::{
	distributions::Uniform,
	prelude::{
		Distribution,
		Rng,
	},
};
use ron::{
	de,
	ser::{
		self,
		PrettyConfig,
	},
};
use std::{
	collections::HashMap,
	fs::{
		self,
		File,
	},
	io,
	path::{Path, PathBuf},
	sync::mpsc::{self, Receiver, TryRecvError},
	thread,
	time::Duration,
};
use url::Url;

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
	let await = options.requests.is_none();

	let handle = thread::spawn(move || request_loop(rx, options));
	if await {
		stdin.read_line(&mut buffer);
		tx.send(CliCommand::End);
	}

	handle.join();
}

enum CliCommand {
	End,
}

fn request_loop(rx: Receiver<CliCommand>, options: Config) {
	let mut easy = Easy::new();
	let url_path = Url::parse(&options.url)
			.unwrap_or_else(|_| panic!("Not given a valid url! Saw: {:?}", &options.url))
			.path()[1..]
			.to_string();

	let dep_list = if options.randomise {
		let file = File::open(options.dep_list_dir.clone().into_owned())
			.expect("Deps list file didn't exist!");
		ron::de::from_reader(file)
			.expect("Deps list must be a ron file of the correct type...")
	} else {
		Dependencies {
			files: vec![
				FileDesc {
					path: Path::new(&url_path).to_path_buf(),
					file_type: FileType::Other,
					deps: DependencyList::Indexed(vec![]),
				}
			],
			name_map: HashMap::default(),
		}
	};

	let available_targets: Vec<&FileDesc> = dep_list.files.iter()
		.filter(|x| x.can_start_chain())
		.collect();

	let mut file_urls = HashMap::<PathBuf, String>::default();
	for fd in &dep_list.files {
		file_urls.insert(
			fd.path.clone(),
			format!("{}/{}", &options.url[..options.url.len() - url_path.len()], fd.path.to_str().expect("Hmm"))
		);
	}

	let mut rng_local = rand::thread_rng();
	let draw = Uniform::new(0, available_targets.len());

	let mut work_queue = vec![];
	let mut visited = vec![false; file_urls.len()];

	#[inline]
	fn enqueue<'a>(
			element: &'a FileDesc,
			queue: &mut Vec<&'a FileDesc>,
			visited: &mut Vec<bool>,
			indexer: &HashMap<String, usize>,) {
		queue.push(element);
		if let Some(index) = indexer.get(&element.path.to_str().unwrap().to_string()) {
			if let Some(el) = visited.get_mut(*index) {
				*el = true;
			}
		}
	}

	let tracker = options.requests;

	enqueue(
		available_targets.get(draw.sample(&mut rng_local))
			.expect("Guaranteed by bounds"),
		&mut work_queue,
		&mut visited,
		&dep_list.name_map);
	
	let mut tracker = tracker.map(|x| x.checked_sub(1).unwrap_or(0));

	let empty_dur = Duration::default();

	loop {
		match rx.try_recv() {
			Err(TryRecvError::Empty) => {
				// Make a request. It's our time!
				let req = work_queue.pop().unwrap();
				let target_url = &file_urls[&req.path];

				// May want to bind write function handlers, idk.
				// Also, bind to append the document needed I guess...
				easy.url(&target_url).unwrap();
				easy.max_send_speed(options.max_up).unwrap();
				easy.max_recv_speed(options.max_down).unwrap();
				// 3 min timeout, just in case a DL gets utterly starved.
				easy.timeout(Duration::from_secs(180)).unwrap();

				if let Err(e) = easy.perform() {
					//eprintln!("error making download: {:?}", e);
				}

				// Go over deps, add them.
				if let DependencyList::Indexed(ref deps) = req.deps {
					for index in deps {
						if !visited[*index] {
							enqueue(
								&dep_list.files[*index],
								&mut work_queue,
								&mut visited,
								&dep_list.name_map);
						}
					}	
				}
				

				// add random element, wipe the visited list.
				if work_queue.is_empty() {
					if tracker == Some(0) {
						break;
					}

					for item in &mut visited {
						*item = false;
					}

					if options.wait_ms > empty_dur {
						// Wait the flow prune time.
						thread::sleep(
							//Duration::new(2, 100000000)
							options.wait_ms
						);
					}
					
					enqueue(
						available_targets.get(draw.sample(&mut rng_local))
							.expect("Guaranteed by bounds"),
						&mut work_queue,
						&mut visited,
						&dep_list.name_map);

					tracker = tracker.map(|x| x.checked_sub(1).unwrap_or(0));
				}
			}
			Ok(CliCommand::End) | Err(_) => {break;},
		}
	}
}
