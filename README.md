tsarchiver
==========

What is tsarchiver
------------------

tsarchiver is a script to archive **tagesschau**, **tagesthemen**, and **nachtmagazin** videos from the [tagesschau.de](https://www.tagesschau.de/) website.
Metadata and subtitles are added to the video files and are stored in a SQLite database.

Usage:
```
$ tsarchiver.py ARCHIVEDIR
```
where `ARCHIVEDIR` is the directory in which to store the downloaded files. Additionally, the script is looking for a SQLite database called `archive.db` inside
this folder. If it can't find one, you will be asked to create one. Then, the script asks for the page index for each show at which to start the archiving.
The index is part of the video domain, for example `https://www.tagesschau.de/multimedia/sendung/ts-34001.html`, the index would be `34001`.

subconvert.py
------------

This script can also be used on its own to convert subtitles from the EBU-TT-D format to the SRT format.
Usage:
```
$ subconvert.py SUBFILE
```
where `SUBFILE` is the subtitle file in the EBU-TT-D (`.xml`) or the WEBVTT (`.xml`) format.
The script also looks for a file called `subignore.txt` inside the script folder. If a subtitle line contains a word or sentence specified in this file, it will be ignored.

Requirements
------------

*   [python3](https://www.python.org/)
*   [ffmpeg](https://www.ffmpeg.org/)
*   [exiftool](https://www.sno.phy.queensu.ca/~phil/exiftool/)

Python packages:
*   [requests](https://pypi.python.org/pypi/requests)
*   [beautifulsoup4](https://pypi.python.org/pypi/beautifulsoup4)
*   [lxml](https://pypi.python.org/pypi/lxml)
*   [pytz](https://pypi.python.org/pypi/pytz)


License
-------

MIT

