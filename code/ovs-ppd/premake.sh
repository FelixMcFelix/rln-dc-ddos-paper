./boot.sh
./configure CFLAGS="-g -O2 -march=native" --enable-Werror --with-linux=/lib/modules/$(uname -r)/build EXTRA_CFLAGS="-O2 -march=native"
