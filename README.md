# Magazine Scanning / OCRing Script

This is a script for converting scans of magazines (or other bound, printed material) into OCRd PDFs for archiving.  It was designed so I could just remove the staples from a magazine, feed the pages through an automatic document feeder, and it would then crop out each page from the spread, rearrange them into the right order, create a PDF, and OCR it.

Some background:  I have a lot of magazines and other printed material, and a small house.  I'm quite enthusiastic about being a digital horder, but I don't want to become an actual horder.  So for several years now, I've been slowly working on how to digitize as much of this material as possible for my own use and then either pass along the originals to somebody else or recycle them.  Plus, having them converted to PDFs and OCRd allows me to then make them searchable, which is great when looking through 60 or 70 years of issues for that one article you need.

It's based around the excellent and awesome ocrmypdf and tesseract for the OCR work.

It's multithreaded where possible, so throw lots of cores at it.  It'll massively speed up the scan to page generation part as well as the OCR.

This is an improved replacement for the hodgepodge of shell scripts and python that I had in the old tool - github.com/ndholmes/magazine-split   But it's still mostly tool for me right now, and as such it does the things I need and doesn't have a whole lot of error checking.  So I hope it's useful, but use at your own risk.

# Getting Things Set Up

So there's a few things you're going to need in order to make this work.  This is as much a reminder to me of how to set things up as anything, so I'm just going to put a bunch of explicit commands here for me to cut/paste in the future.  

First step?  Obviously clone this repo somewhere.  Guessing you probably already did that.

## Tesseract

You're also going to want the latest-ish version of tesseract.  I'm currently on 5.3.1

```
sudo add-apt-repository ppa:alex-p/tesseract-ocr5
sudo apt install tesseract-ocr
```

## Python 3.11

I highly recommend running this in a venv, and you're really probably going to want python 3.11 or better for performance reasons.  Also that's what I've tested with.  It probably will run under other versions, but you're kind of on your own there.  This is all going to assume you're running Ubuntu or some other Debian-based distro.

```
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.11 python3.11-venv
```

Now, set up that venv and activate it.  I build mine in the same directory as I check out the magazine-ocr project, so it's magazine-ocr/ocr-venv/...

```
python3.11 -m venv ocr-venv
source ocr-venv/bin/activate
```

## Additional Python Packages

Now that you've activated your venv (right?!?), we need to install some dependencies.  They're in requirements.txt
```
python -m pip install -r requirements.txt
```
# Actually Running It


## Command Line Options Summary

| Opt | Reqd | Description                                                                           |
|-----|------|---------------------------------------------------------------------------------------|
| -i  |  Y   | Input directory containing the source images - ex: -i ~/data/ocr/input                |
| -o  |  Y   | Output path for final PDF - ex: -o ~/data/ocr/output/rfr-2000-03.pdf                  |
| -m  |  Y   | Page splitting algorithm.  See below for details                                      |
| -a  |  N   | Archive conversion command and source images.  Defaults to false                      |
| -d  |  N   | DPI that should be used to scale images into the PDF.  300 is default                 |
| -e  |  N   | Delete source images upon successful completion.  Defaults to false                   |
| -f  |  N   | File spec for input source images.  By default, jpg, png, and tif are searched.  This would be things like "*.GIF" to just grab all GIFs.  Is case sensitive. |
| -j  |  N   | JPEG quality that should be used to save page images in PDF.  80 is default           |
| -s  |  N   | Input file sort order - 'name' or 'date' - name is default                            |
| -v  |  N   | Debug verbosity.  1 is informative.  2 leaves intermediate artifacts without cleaning up. |
| -x  |  N   | Transforms to be performed on "front" side scans                                      |
| -y  |  N   | Transforms to be performed on "back" side scans                                       |
| -z  |  N   | Transforms to be performed on all scans                                               |

## Input / Output

-i is how you specify where your input images live.  By default, it will search for all files with jpg, JPG, png, PNG, tif, and TIF extensions.  If you want to specify a glob pattern, use the -f option (such as if you want '*.TIFF' or something perverse).

-o is where the output PDF should go, complete with filename.

-a will archive off what options the script was run with, as well as the original source iamges.  It uses the base name (no extension) from the output PDF path and creates a directory of that name in the same output directory as the PDF.

If you want to automatically get rid of your input images once you've successfully processed them (such as to clear out an input directory for the next batch), -e will do just that.

## Sort Mode

Fundamentally, magazine-ocr needs to sort the incoming scans to try to make sense of the order they were scanned in.  It supports two modes - name, which is the default, and date.  Name is exactly what you think it is - it will sort the filenames in order, so something like P3700037F is presumed to come before P3700038B.  Date uses the file modification date to try to figure out which order you scanned them in.  Personally, I always try to shoot for name order sorting.

## Page Split Algorithm

The -m option is key to operation of magazine-ocr and tells the program where it should look to find pages in the scans.

Current Options:

fbfb - Short for "front, back, front, back" this is going to be typical for either dual-sided scanners (such as a Xerox Documate 4790) or duplex scanners (Epson WF-7820).  This expects that the magazine has been unbound and the first file will be the cover, the second file will be the back of the cover, the third file will be the front side of the first inside sheet, the fourth file will be the back side of the first inside sheet, etc.  It also assumes that there are two pages per scanned sheet, and the dividing line is in the middle of the image.

ffbb - Short for "front, front, back, back" this would be used with single-sided scanning through an automatic document feeder (ADF).  Again, this assumes the magazine has been unbound.  However, it then assumes you scan all of one side of the magazine, and then you flip the whole stack over and scan all of the other sides.  This is useful on magazines that tend to jam or not feed when going through a duplexer mechanism on an ADF.

frbr - Same as "front, front, back, back" (ffbb), but with reversed page order.  This would be used in the same situation as ffbb, but on a dual-sided scanner than only has a working backside imager.

Yes, I'll add more in the future, but for the moment that's what I needed so that's what exist.

## Transforms

In general, magazine-ocr expects input scans to be side-by-side pages with the division right in the center.  (See "Split Mode" for more details.)  Sometimes scanners don't want to give us images that way - they're rotated by some multiple of 90, or they've got some dead space on the edges because magazines aren't perfectly the size of the scanner platten, etc.  magazine-ocr allows you to perform simple transforms on the source images before they're chunked down into pages.

Command line options -x, -y, and -z can be used to apply transformations to the source images.  -x applies to scans that are deemed "front" and -y applies to scans that are deemed "back".  This makes sense when you have a scanner that's either dual-sided (such as the Documate 4790 that we're working with) or has a duplexer (such as my Epson WF-7820).  -z will apply a transform to all scans.  Any transforms in -x or -y are applied first, and then any transforms in -z.

The transform strings are a list of transform characters and their arguments, all mushed together.  They will be executed in the order listed.

| Xform | Args | Description                                                                           |
|-----|------|---------------------------------------------------------------------------------------|
|  c  |  (x-width)x(y-height)+(x-offset)+(y-offset)   | CROP - cuts an image to x-width by y-height.  0,0 is the upper left corner of the image.  Offsets will move the cropped region over and/or down.  So 3300x1100+0+0 would be an example. |
|  r  |  (angle)   | Rotates the image (angle) degrees counterclockwise.  Only positive numbers accepted. |
|  s  |  (x-width)x(y-height)  or (percent)%   | Scales an image.  So if you started with a 300dpi scan and only wanted to use it at 200 dpi, specify s67% |

Examples:  c3250x4850+20+0r270s67%  will crop an image to 3250 wide by 4850 tall, with an offset of 20 pixels from the left and 0 pixels from the top.  It will then rotate it 270 degrees counterclockwise, and scale it by 67%.  

# Example

Here's some cut/paste bait to start from:

```
python3 magazine-ocr.py -i ~/data/ocr/input/ -s name -m fbfb -x "c3250x4850+20+0r270s67%" -y "c3250x4850+20+0r90s67%" -d 200 -o ~/data/ocr/output/rfr-2000-03.pdf -a
```

# License

Copyright 2023 Nathan D. Holmes (maverick@drgw.net).  GPL v3, per License file.  If you've got useful improvements or just find it's come in handy for your own data hording, drop me a note.


