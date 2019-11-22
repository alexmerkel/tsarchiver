#!/usr/bin/env python3
'''subconverter - convert subtitles to the SRT format'''

import os
import sys
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------- #
def parseEBU(subtitles):
    '''Parse EBU-TT formatted subtitles to intermediate format

    :param subtitles: Subtitles in the EBU-TT format
    :type subtitles: string

    :returns: Intermediate format
    :rtype: list of dictionaries
    '''
    colors = {}
    subs = []
    ebutt = BeautifulSoup(subtitles, "xml")
    #Get colors
    for style in ebutt.find("tt:styling").find_all("tt:style"):
        if "tts:color" in style.attrs:
            colors[style.attrs["xml:id"]] = style.attrs["tts:color"]
    #Loop through
    for p in ebutt.find("tt:div").find_all("tt:p"):
        #Get begin and end times
        attrs = p.attrs
        begin = attrs["begin"].replace('.', ',')
        if not begin.startswith("0"):
            begin = '0' + begin[1:]
        end = attrs["end"].replace('.', ',')
        if not end.startswith("0"):
            end = '0' + begin[1:]
        sub = {"begin" : begin, "end" : end}
        #Loop through items inside p
        items = p.findChildren()
        lines = []
        for item in items:
            #span element: text
            if item.name == "span":
                lines.append({"color" : colors[item.attrs["style"]], "text" : item.text})
            #br: insert line break
            elif item.name == "br":
                lines.append({"text" : "\n"})
        if lines:
            sub["lines"] = lines
            subs.append(sub)

    return subs
# ########################################################################### #

# --------------------------------------------------------------------------- #
def parseVTT(subtitles):
    '''Parse WEBVTT formatted subtitles to intermediate format

    :param subtitles: Subtitles in the WEBVTT format
    :type subtitles: string

    :returns: Intermediate format
    :rtype: list of dictionaries
    '''
    subs = []
    lines = []
    begin = ""
    end = ""
    for line in subtitles.splitlines():
        #Ignore header
        if line == "WEBVTT":
            continue
        #Ignore empty lines
        if not line:
            continue
        #If line starts with Sub, save previous sub if any
        if line.startswith("Sub"):
            if lines and begin and end:
                subs.append({"begin" : begin, "end" : end, "lines" : lines})
            lines = []
            begin = ""
            end = ""
            continue
        #Get time codes
        if "-->" in line:
            [begin, end] = line.split("-->", 1)
            begin = begin.strip().replace('.', ',')
            if not begin.startswith("0"):
                begin = '0' + begin[1:]
            end = end.strip().replace('.', ',')
            if not end.startswith("0"):
                end = '0' + begin[1:]
            continue
        #Normal line
        #If already a line in this block, add line break
        if lines:
            lines.append({"text" : "\n"})
        lines.append({"text" : line})

    return subs
# ########################################################################### #

# --------------------------------------------------------------------------- #
def generateSrt(subs):
    '''Generate SRT formatted subtitles from intermediate format

    :param subs: Intermediate format
    :type subs: list of dictionaries

    :returns: List with the srt subtitles and the transcript as items
    :rtype: list of string
    '''
    #Read lines to ingore
    excludeLines = []
    excludeFile = os.path.join(os.path.dirname(os.path.realpath(__file__)), "subignore.txt")
    try:
        with open(excludeFile, 'r') as f:
            excludeLines = [l.strip() for l in f.readlines()]
    except IOError:
        pass
    counter = 0
    srt = ""
    trans = ""

    #Generate srt
    for sub in subs:
        text = ""
        textRaw = ""
        if not "lines" in sub or not sub["lines"]:
            continue
        ignore = False
        for line in sub["lines"]:
            #Check if to be ignored
            if any(e in line["text"] for e in excludeLines):
                ignore = True
                break
            #Check if color is given
            if "color" in line:
                text += "<font color=\"{}\">{}</font>".format(line["color"], line["text"])
                textRaw += line["text"]
            else:
                text += line["text"]
                textRaw += line["text"]
        if not ignore:
            counter += 1
            srt += "{}\n{} --> {}\n{}\n\n".format(counter, sub["begin"], sub["end"], text)
            trans += "{}\n\n".format(textRaw)

    return [srt, trans]
# ########################################################################### #

# --------------------------------------------------------------------------- #
def convertEBU(subtitles):
    '''Convert subtitle from the EBU-TT to the SRT format

    :param subtitles: EBU-TT formated subtitles
    :type subtitles: string

    :returns: List with the srt subtitles and the transcript as items
    :rtype: list of string
    '''
    subs = parseEBU(subtitles)
    return generateSrt(subs)
# ########################################################################### #

# --------------------------------------------------------------------------- #
def main(args):
    '''Convert subtitle file to the SRT format

    :param args: The command line arguments given by the user
    :type args: list
    '''
    #Read file if one is given, else throw an error
    try:
        with open(args[1], 'r') as f:
            raw = f.read()
    except IndexError:
        print("Usage: subconvert.py SUBFILE")
        return
    except IOError:
        print("File not found '{}'".format(args[1]))
        print("Usage: subconvert.py SUBFILE")
        return
    subFileComp = os.path.splitext(args[1])

    #Check file format
    if subFileComp[1] == ".xml":
        #Parse EBU-TT-D
        subs = parseEBU(raw)
    elif subFileComp[1] == ".vtt":
        #Parse WEBVTT
        subs = parseVTT(raw)
    else:
        #Unknown file, throw error
        print("Unknown file, currently EBU-TT-D (.xml) and WEBVTT (.vtt) are supported")

    #Generate srt
    [srt, _] = generateSrt(subs)
    #Save .srt file
    srtFile = subFileComp[0] + ".srt"
    with open(srtFile, 'w', encoding='utf8') as f:
        f.write(srt)
# ########################################################################### #

# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    try:
        main(sys.argv)
    except KeyboardInterrupt:
        print("Aborted!")
# ########################################################################### #
