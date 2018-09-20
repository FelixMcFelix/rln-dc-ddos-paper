use config::Config;
use content::{
	Dependencies,
	FileDesc,
};
use parking_lot::RwLock;
use rayon::{
	iter,
	prelude::*,
};
use std::{
	collections::HashMap,
	fs,
	io::{
		self,
		Error,
		ErrorKind,
	},
	path::Path,
	sync::Arc,
};
use url::Url;

pub fn walk(config: &Config<'static>) -> io::Result<Dependencies> {
	let root_str = config.http_dir.clone().into_owned();
	let root = Path::new(&root_str).to_path_buf();
	let url_base = Url::parse(&config.url)
		.expect(
			&format!("Url paramater \"{:?}\" was invalid", &config.url)
		);

	let mut dirs = vec![root.clone()];
	let mut files = vec![];

	while !dirs.is_empty() {
		let curr = {
			dirs.pop()
				.expect("Known to be non-empty.")
		};

		println!("{:?}", curr);

		for element in fs::read_dir(curr)? {
			let element = element?;
			let path = element.path();

			// println!("{:?}", path);

			if path.is_dir() {
				dirs.push(path);
			} else {
				files.push(path);
			}
		}
	}

	let map = Arc::new(RwLock::new(
		HashMap::<String, usize>::new()
	));

	let file_count = files.len();

	let descs: Vec<FileDesc> = files.par_iter_mut()
		.zip(iter::repeatn(map.clone(), file_count))
		.map(|(p, lock)| {
			let out = FileDesc::new(p, &root, &url_base);

			{
				let mut write_map = lock.write();
				let index = write_map.len();
				write_map.insert(out.get_path(), index);
			}

			out
		})
		.collect();

	let indexed: Vec<FileDesc> = descs.par_iter()
		.zip(iter::repeatn(map.clone(), file_count))
		.map(|(desc, lock)| {
			let mut desc = desc.clone();
			let map_read = lock.read();
			desc.to_indexed(&map_read);

			desc
		})
		.collect();

	// println!("{:?}", descs);
	// println!("---");
	// println!("{:?}", indexed);

	Arc::try_unwrap(map)
		.map(|name_map_lock| {
			Dependencies{
				files: indexed,
				name_map: name_map_lock.into_inner(),
			}
		})
		.map_err(|_| Error::new(
			ErrorKind::Other,
			"Couldn't strip the lock from final map...")
		)
}