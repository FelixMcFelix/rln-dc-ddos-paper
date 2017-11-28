# Open vSwitch (with some modifications)

Open vSwitch modified to support a new action, "probdrop" (on some integer probability between 0 and 2^32 - 1).

First, remove old mininet:
```sh
sudo apt-get remove openvswitch-common openvswitch-datapath-dkms openvswitch-controller openvswitch-pki openvswitch-switch
```

To get it going in mininet:
```sh
./premake.sh
make
sudo make install
sudo make modules_install
sudo rmmod openvswitch
sudo sh kernupdate.sh
```