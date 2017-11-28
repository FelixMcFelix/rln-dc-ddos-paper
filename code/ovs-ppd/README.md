# Open vSwitch (with some modifications)

Open vSwitch modified to support a new action, "probdrop" (on some integer probability between 0 and 2^32 - 1).

To get it going in mininet:
```sh
./premake.sh
sudo make install
sudo sh kernupdate.sh
```