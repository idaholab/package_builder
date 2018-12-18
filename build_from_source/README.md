# Build from Source
The following instructions can be used to build everything that ends up in our redistributable package.

To get started, be sure to have a clean environment. That is, a machine which is more or less 'right out of the box'. Your goal should be to produce a compiler stack you can transport to another machine of the same arch/build and just have it work. The best way to do this, is to always work with a vanilla install of the target OS. Not your run of the mill, day-to-day machine which might have a great many other packages in play.

## Prerequisites
Due to the many different ways packages can be named, you may have to search for your specific operating system's equivalent. The following two popular distribution are provided as an example.

Install the following necessary dependencies to build from source:

Debian based:
```bash
apt-get install \
git \
curl \
patch \
build-essential \
gfortran \
flex \
bison \
tcl-dev \
tk-dev \
python-dev \
libblas-dev \
liblapack-dev \
freeglut3-dev \
libxt-dev \
libncurses5-dev \
libedit-dev \
zlib1g-dev \
libperl-dev
```

RedHat (CentOS):
```bash
yum install \
git \
curl \
patch \
gcc \
gcc-c++ \
gcc-gfortran \
flex \
bison \
tcl-devel \
tk-devel \
python-devel \
libblas-devel \
liblapack-devel \
freeglut3-devel \
libXt-devel \
ncurses-devel \
libedit-devel \
zlib-devel \
libperl-devel
```

For Darwin machines, simply having Xcode and Xcode Command Line Tools package will suffice.

Hopefully, thats everything your machine requires, but in practice there's always something. If that 'something' comes up, the script will fail and inform you of the error. Usually that will be enough to understand what additional dependency is needed to continue. Once you do satisfy that dependency, re-running the script will pick up where it left off.

## Clone Repo
Clone the repository:
```bash
git clone https://github.com/idaholab/package_builder.git
```

## Create Target Location
Create and chown the target directory:
```bash
sudo mkdir -p /opt/moose
sudo chown -R <your user id> /opt/moose
```
/opt/moose can be any location you wish. But it is permanent. Many of the libraries we are about to build will expect this location to exist (some libraries will link with absolute paths instead of relative). If you are building this redistributable with the desire to install within an HPC cluster environment, keep in mind the target directory should be reachable by all your compute nodes.

Chown the target directory so that the scripts we are about to execute do not require root privileges. Otherwise you will be asked for sudo's password an untold number of times. But most importantly we do it because no one should trust a script found on the internet with 'root' privileges.

## Execute
Again, do not run this script as root. It might work, but thats just bad admin practices.
```bash
cd package_builder/build_from_source
./make_all.py --prefix /opt/moose --max-jobs <int> --cpu-count <int>
```
Some info about those options:
 --max-jobs   build this many modules at the same time
 --cpu-count  how many processors to allow each module to consume

When or if a problem arises, it will normally be a dependency issue. What ever the fix may be, once solved, simply re-execute the same ./make_all.py script and the build will pick up where it left off.

On my test workstation with 12 real cores available, I've found --max-jobs set at 4 and --cpu-count set at 6 completes the entire package in roughly 2 1/2 hours.

Once finished, if there were any failures along the way, there may be leftover files/directories in your temporary directory. Everything that was downloaded will also still exist (/tmp/moose_package_download_temp). The moose_package_download_temp directory does not get deleted by design. This allows for rapid building on a machine in which failures may be frequent.

On Darwin machines the temp directory is a bit more obscure. /tmp exists... and is writable, but is not 'truly' the correct temp path location. You can figure out what your true temporary location is by running the following python commands:
```python
import tempfile
print tempfile.gettempdir()
```

## Test the Compiler Stack
Now that everything has been built, you should test this compiler stack by sourcing the moose_profile and attempt to build libMesh/MOOSE and run the tests:

```bash
. /opt/moose/environments/moose_profile
git clone https://github.com/idaholab/moose
cd moose/scripts
./update_and_rebuild_libmesh.sh
cd ../test
make -j $MOOSE_JOBS
./run_tests -j $MOOSE_JOBS
```

If all goes well, it should be safe to to create a redistributable package. The package_builder repository contains a helper script for this process. Please see the README.md file located in package_builder/create_redistributable/.

