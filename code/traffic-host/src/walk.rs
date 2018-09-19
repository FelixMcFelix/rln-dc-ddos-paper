use config::Config;
use std::{
	fs,
	io,
	path::Path,
};

pub fn walk(config: &Config<'static>) -> io::Result<()> {
	let root_str = config.http_dir.clone().into_owned();
	let root = Path::new(&root_str).to_path_buf();

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

	while !files.is_empty() {
		let curr = {
			files.pop()
				.expect("Known to be non-empty.")
		};

		println!("{:?}", curr.strip_prefix(&root).expect(""));
	}
	// .strip_prefix(root)
	// .expect("All are children of the root...")

	Ok(())
}