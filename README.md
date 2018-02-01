# DGS-Graphstream

Create animation of network partition assignments. First processes network file and assignments into DGS file format, then uses GraphStream to animate each frame, finally frames are stitched together.

![screenshot](./samples/4_partitions.svg)

## Getting started

### 1. Installing dependencies

DGS-Graphstream depends on the following programs that first need to be installed:

#### [OSLOM2](http://www.oslom.org/software.htm)

```shell
wget http://www.oslom.org/code/OSLOM2.tar.gz
tar -xvzf OSLOM2.tar.gz
cd OSLOM2/
./compile_all.sh
```

#### [Infomap](http://www.mapequation.org/code.html#Linux)

```shell
wget http://www.mapequation.org/downloads/Infomap.zip
unzip Infomap.zip -d Infomap
cd Infomap/
make
```

#### [Graphviz](https://gitlab.com/paulantoineb/graphviz) ([dependencies](https://graphviz.gitlab.io/_pages/Download/Download_source.html))

This fork of Graphviz is required. It modifies `gvmap` to color individual nodes instead of clusters.

```shell
# depends on "libtool", "automake", and "autoconf"
git clone https://gitlab.com/paulantoineb/graphviz.git
cd graphviz/
./autogen.sh
./configure
make
```

`autoconf` can be installed with the following command if required.

```shell
# Ubuntu
sudo apt-get install autoconf
```

`gvmap` requires `gts` to be installed. If you see the line *"gts: No (gts library not available)"* when running `./autogen.sh`, you need to install `gts` and then rerun `./autogen.sh`. You will see *"gts: Yes"* when it is installed.

```shell
# Ubuntu
sudo apt install libgts-dev
sudo pkg-config --libs gts
sudo pkg-config --cflags gts
```

#### [ImageMagick](https://www.imagemagick.org/script/install-source.php#unix)

The ImageMagick `montage` utility is used to stitch graph images together.

#### [FFmpeg](https://www.ffmpeg.org/download.html)

`FFmpeg` is used to combine frames into a video.

### 2. Installing dgs-graphstream    

```shell
# Setting up virtualenv
sudo pip3 install virtualenv
virtualenv -p python3 ~/env
source ~/env/bin/activate

# Getting dgs-graphstream and installing python requirements
git clone https://github.com/paulantoineb/dgs-graphstream.git
cd dgs-graphstream/
pip3 install -r requirements.txt

# Building the Java library (depends on the `Java JDK` and `ant`)
cd dgs-graphstream/
ant
cd ..
```

### 3. Updating the configuration file

After installing the dependencies and dgs-graphstream , update the config.ini file with the installation directories of `OSLOM2`, `infomap` and `gvmap`:
```
[install_dirs]
oslom2 = /home/paulantoineb/bin/OSLOM2/
infomap = /home/paulantoineb/bin/infomap/
gvmap = /home/paulantoineb/bin/graphviz/cmd/gvmap/
```

## Generate an animation

Run the following commands:
```shell
source env/bin/activate
./genGraphStream.py inputs/network_1.txt -f metis -a ./inputs/assignments.txt  -o output/ -c oslom2 --video output/vid.mp4 --pdf 20  
```

The output directory should now contain the following files:
* `*.dgs` - the files DGS files for each partition built by combining the METIS network file and the assignments.
* `frames_partition/` - individual frames for each step in the DGS file. Prefixed with the partition number, eg. `p1_*.png`
* `frames_joined/` - the frames from the folder above are joined to produce a single video frame. The video frame is stepped by node placement from the assignments file.
* `pdf/` - the same video frames as above but as pdfs
* `vid.mp4` - the video frames animated into an MP4 for playback

## Using the Java GraphStream renderer manually

The GraphStream renderer is already executed when generating the animation above. To generate the frames manually,
for example to experiment with the LinLog layout, the jar program can be executed directly.

```
$ java -jar "dgs-graphstream/dist/dgs-graphstream.jar" -h
Missing required option: -dgs

Missing required option: -out

usage: DgsGraphStreamAnimate.jar [OPTIONS]...
-dgs <arg>          input GraphStream DGS file
-out <arg>          frame filenames are prepended with this path
-layout <arg>       layout type to use. options: [springbox|linlog]. default: springbox
-seed <arg>         random seed for the layout
-force <arg>        force for LinLog layout
-a <arg>            attraction factor for LinLog layout
-r <arg>            repulsion factor for LinLog layout
-theta <arg>        theta for LinLog layout
-node_size <arg>    node size
-edge_size <arg>    edge size
-width <arg>        image width
-height <arg>       image height
-mode <arg>         mode. options: [images|dot]. default: images
-dotfile <arg>      output dot file
-display screen     layout option to use. options: [screen]
-h,-help            display this help and exit
```

When used in this way, the `./genGraphStream.py` script can be used to create the DGS file, which is then fed into
the JAR to generate the frames and finally back into `./genGraphStream.py` to join them together.

## Authors

* Sami Barakat (<sami@sbarakat.co.uk>)
* Paul-Antoine Bittner

Licensed under the MIT license. See the [LICENSE](https://github.com/sbarakat/dgs-graphstream/blob/master/LICENSE) file for further details.
