use cssparser::{
	Parser,
	ParserInput,
};
use select::{
	document::Document,
	predicate::{Name, Or},
};
use std::{
	collections::HashMap,
	fs::{
		read,
		File,
	},
	path::{Path, PathBuf},
};
use url::Url;

#[derive(Copy, Clone, Debug, Deserialize, Serialize)]
pub enum FileType {
	Page,
	Js,
	Stylesheet,
	Image,
	Other,
}

impl FileType {
	pub fn can_start_chain(&self) -> bool {
		use content::FileType::*;
		match self {
			Page | Image | Other => true,
			_ => false
		}
	}
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub enum DependencyList {
	Canon(Vec<String>),
	Indexed(Vec<usize>),
}

impl DependencyList {
	fn new<P: AsRef<Path>>(filepath: P, file_type: FileType, base: &Url, curr_url: &Url) -> Self {
		use content::FileType::*;
		let deps = match file_type {
			Page => html_deps,
			Js => js_deps,
			Stylesheet => css_deps,
			_ => other_deps,
		}(filepath.as_ref(), base, curr_url);

		DependencyList::Canon(deps)
	}

	fn to_indexed(&self, map: &HashMap<String, usize>) -> Self {
		use content::DependencyList::*;
		let list = match self {
			Canon(l) => l.iter()
				.filter_map(|s| map.get(s))
				.cloned()
				.collect(),
			Indexed(l) => l.clone(),
		};
		Indexed(list) //Hmm
	}
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct FileDesc {
	pub path: PathBuf,
	pub file_type: FileType,
	pub deps: DependencyList,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Dependencies {
	pub files: Vec<FileDesc>,
	pub name_map: HashMap<String, usize>,
}

impl FileDesc {
	pub fn new<P: AsRef<Path>, Q: AsRef<Path>>(filepath: P, root: Q, base: &Url) -> Self {
		let path = filepath.as_ref()
			.strip_prefix(root)
			.expect("File must be a child of the root directory.")
			.to_path_buf();
		let curr_url = base.join(path.to_str().expect("Path must be valid UTF8."))
			.expect("Valid base + valid directory.");
		let file_type = classify_file_type(&path);
		let deps = DependencyList::new(filepath, file_type, base, &curr_url);

		FileDesc {
			path,
			file_type,
			deps,
		}
	}

	pub fn get_path(&self) -> String {
		self.path
			.to_str()
			.expect("Somehow, invalid UTF path")
			.to_string()
	}

	pub fn to_indexed(&mut self, map: &HashMap<String, usize>){
		self.deps = self.deps.to_indexed(map);
	}

	pub fn can_start_chain(&self) -> bool {
		self.file_type.can_start_chain()
	}
}

fn classify_file_type(path: &PathBuf) -> FileType {
	match path.extension() {
		Some(os_str) => match os_str.to_str() {
			Some("html") | Some("htm") => {
				FileType::Page
			},
			Some("css") => {
				FileType::Stylesheet
			},
			Some("js") => {
				FileType::Js
			},
			Some("png") | Some("jpeg") | Some("ico") |
			Some("jpg") | Some("gif") => {
				FileType::Image	
			},
			_ => {
				FileType::Other
			}
		},
		_ => {
			FileType::Other
		}
	}
}

fn html_deps(path: &Path, base: &Url, curr_url: &Url) -> Vec<String> {
	let mut out = vec![];
	let file = File::open(path)
		.expect("file guaranteed to exist");

	let doc = Document::from_read(file);

	if let Ok(doc) = doc {
		// link: href tags. Css, xml, etc.
		out.extend(doc.find(Name("link"))
			.filter_map(|tag| tag.attr("href"))
			.filter_map(|s| localise_url(s, base, curr_url))
		);

		// img + script: src
		out.extend(doc.find(Or(Name("img"), Name("script")))
			.filter_map(|tag| tag.attr("src"))
			.filter_map(|s| localise_url(s, base, curr_url))
		);
	}

	out
}

fn js_deps(path: &Path, base: &Url, curr_url: &Url) -> Vec<String> {
	// TODO
	vec![]
}

fn css_deps(path: &Path, base: &Url, curr_url: &Url) -> Vec<String> {
	// TODO?
	
	// let file = fs::read(path)
	// 	.expect("file guaranteed to exist");
	// let mut input = ParserInput::new(&file);
	// let mut parser = Parser::new(&mut input);

	// while let Ok(token) = parser::next() {

	// }

	vec![]
}

fn localise_url(url: &str, base: &Url, curr_url: &Url) -> Option<String> {
	// If this is a relative path, canonise it.
	// (i.e., remove all the ../../a.png etc.)
	// From there, if domain is correct then strip it, and output.
	// If domain isn't the right base, then return None.

	curr_url.join(url)
		.ok()
		.and_then(|dep_addr|
			if dep_addr.host() == base.host() {
				Some(dep_addr.path()[1..].to_string())
			} else {
				None
			}
		)
}

fn other_deps(_path: &Path, _base: &Url, curr_url: &Url) -> Vec<String> {
	vec![]
}