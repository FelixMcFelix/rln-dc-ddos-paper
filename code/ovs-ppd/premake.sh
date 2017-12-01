./boot.sh
./configure --prefix=/usr/local --with-linux=/lib/modules/`uname -r`/build CFLAGS="-g" EXTRA_CFLAGS="-g" --enable-Werror
#./configure --prefix=/usr/local CFLAGS="-g" EXTRA_CFLAGS="-g"
