#!/usr/bin/env python3

# subconvert 1.0

import os
import sys
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------- #
def convertEBU(subtitles):
    trans = ""
    srt = ""
    counter = 0
    colors = {}
    ebutt = BeautifulSoup(subtitles, "xml")
    #Get colors
    for style in ebutt.find("tt:styling").find_all("tt:style"):
        if "tts:color" in style.attrs:
            colors[style.attrs["xml:id"]] = style.attrs["tts:color"]
    #Loop through
    for p in ebutt.find("tt:div").find_all("tt:p"):
        text = ""
        textRaw = ""
        #Get begin and end times
        attrs = p.attrs
        begin = attrs["begin"].replace('.', ',')
        if not begin.startswith("0"):
            begin = '0' + begin[1:]
        end = attrs["end"].replace('.', ',')
        if not end.startswith("0"):
            end = '0' + begin[1:]
        #Loop through items inside p
        items = p.findChildren()
        for item in items:
            #span element: text
            if item.name == "span":
                #Check if in exclude file
                excludeFile = os.path.join(os.path.dirname(os.path.realpath(__file__)), "subignore.txt")
                if os.path.isfile(excludeFile):
                    found = False
                    with open(excludeFile, 'r') as f:
                        for line in f.readlines():
                            if line.strip() in item.text:
                                found = True
                                break
                    if found:
                        text = ""
                        textRaw = ""
                        break
                text += "<font color=\"{}\">{}</font>".format(colors[item.attrs["style"]], item.text)
                textRaw += item.text
            #br: insert line break
            elif item.name == "br":
                text += "\n"
                textRaw += "\n"
        if text:
            counter += 1
            srt += "{}\n{} --> {}\n{}\n\n".format(counter, begin, end, text)
            trans += "{}\n\n".format(textRaw)

    return [srt, trans]
# ########################################################################### #

# --------------------------------------------------------------------------- #
def main(args):
    if len(args) == 1 or not os.path.isfile(args[1]):
        print("Usage: subconvert.py XMLSUB")

    with open(args[1], 'r') as f:
        raw = f.read()

    [srt, _] = convertEBU(raw)

    subFileComp = os.path.splitext(args[1])
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
