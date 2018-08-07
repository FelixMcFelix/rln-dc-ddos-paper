extern crate reqwest;
extern crate tokio;

mod config;

pub use config::Config;

pub fn run(options: config::Config) {
	println!("Hello, world!");

    println!("{:?}", options);

    // TODO: swap this over to use libcurl since that's nicer
    // and lets me ratelimit etc in a way that hyper doesn't. :)

	match reqwest::get("https://mcfelix.me") {
		Ok(mut resp) => {
			println!("url: {}", &resp.url());
			println!("status: {}", &resp.status());
			println!("headers: {}", &resp.headers());
			println!("text: {}", &resp.text().unwrap_or("None".into()));
		},
		Err(e) => println!("Error encountered: {:?}", e)
	}
}
