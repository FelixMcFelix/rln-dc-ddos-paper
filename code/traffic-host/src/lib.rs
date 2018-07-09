extern crate reqwest;
extern crate tokio;

pub fn run() {
	println!("Hello, world!");

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