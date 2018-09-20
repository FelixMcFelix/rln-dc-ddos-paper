use std::borrow::Cow;

#[derive(Debug)]
pub struct Config<'a> {
	/// Path to the dependency list structure.
    pub dep_list_dir: Cow<'a, str>,

    /// Directory to use as basis for requests.
    pub http_dir: Cow<'a, str>,

    /// Maximum download rate, in bytes/s.
    pub max_down: u64,

    /// Maximum upload rate, in bytes/s.
    pub max_up: u64,

    /// Base url for the domain to make requests from.
    pub url: Cow<'a, str>,
}

