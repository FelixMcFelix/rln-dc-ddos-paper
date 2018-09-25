mkdir -p htdocs

# Build a blog-like site in place
hugo -b "http://10.0.0.1/" -d "../htdocs" -s "./mcfelix.me"

# Download any extra binary files to spice life up a little...
wget -P "htdocs" "ftp://ftp.mirrorservice.org/sites/sourceware.org/pub/gcc/releases/gcc-8.2.0/gcc-8.2.0.tar.gz" 

cargo run --release -- -b
