#!/usr/bin/env python3

# tsarchiver 0.1

import os
import sys
import json
from datetime import datetime
import subprocess
import shutil
import pytz
from bs4 import BeautifulSoup
import requests

# --------------------------------------------------------------------------- #
# Archive a news site
def archive(argv):
    #Get directory
    if len(argv) > 1:
        directory = argv[1]
    else:
        directory = os.getcwd()
    lastFile = os.path.join(directory, "last.json")

    try:
        #Load last times
        with open(lastFile, 'r') as f:
            last = json.load(f)
        #Get shows
        getShows(directory, last)
        #Save new last values
        with open(lastFile, 'w', encoding='utf8') as f:
            json.dump(last, f, ensure_ascii=False)
    except FileNotFoundError:
        print("Error: No last.json found in directory")
    except json.decoder.JSONDecodeError:
        print("Error: last.json unreadable")
# ########################################################################### #

# --------------------------------------------------------------------------- #
# Get the info for the new shows and update the last ID
def getShows(directory, last):
    #Get Tagesschau
    for i in range(last['ts']+2, last['ts']+50, 2):
        url = "https://www.tagesschau.de/multimedia/sendung/ts-{}.html".format(i)
        r = requests.get(url)
        if r.status_code == 404:
            continue
        page = BeautifulSoup(r.text, features="html.parser")
        title = page.title.text
        if "20:00" in title:
            dateString = title.split("tagesschau", 1)[1].split("Uhr", 1)[0].strip()
            [date, timestamp, localtime, metadate] = convertDate(dateString)
            content = page.body.find('div', attrs={'class' : 'inhalt'})
            saveShow("ts20", date, timestamp, localtime, metadate, content, directory)
            last['ts'] = i
    #Get Tagesthemen
    for i in range(last['tt']+2, last['tt']+8, 2):
        url = "https://www.tagesschau.de/multimedia/sendung/tt-{}.html".format(i)
        r = requests.get(url)
        if r.status_code == 404:
            continue
        page = BeautifulSoup(r.text, features="html.parser")
        title = page.title.text
        dateString = title.split("tagesthemen", 1)[1].split("Uhr", 1)[0].strip()
        [date, timestamp, localtime, metadate] = convertDate(dateString)
        content = page.body.find('div', attrs={'class' : 'inhalt'})
        saveShow("tt", date, timestamp, localtime, metadate, content, directory)
        last['tt'] = i
    #Get Nachtmagazin
    for i in range(last['nm']+2, last['nm']+8, 2):
        url = "https://www.tagesschau.de/multimedia/sendung/nm-{}.html".format(i)
        r = requests.get(url)
        if r.status_code == 404:
            continue
        page = BeautifulSoup(r.text, features="html.parser")
        title = page.title.text
        dateString = title.split("nachtmagazin", 1)[1].split("Uhr", 1)[0].strip()
        [date, timestamp, localtime, metadate] = convertDate(dateString)
        content = page.body.find('div', attrs={'class' : 'inhalt'})
        saveShow("nm", date, timestamp, localtime, metadate, content, directory)
        last['nm'] = i
# ########################################################################### #

# --------------------------------------------------------------------------- #
# Download show and parse show info
def saveShow(show, date, timestamp, localtime, metadate, desc, directory):
    #Print status
    print("Get {} from {}".format(show, localtime))
    #Initialize info json
    info = {}
    info["show"] = show
    info["timestamp"] = timestamp
    info["localtime"] = localtime
    info["metadate"] = metadate
    #Extract topics
    teaser = desc.find_all('p', attrs={'class' : 'teasertext'})
    info["topics"] = teaser[0].text.split(':', 1)[1].strip()
    #Extract notes
    if "Hinweis" in teaser[1].text:
        info["note"] = teaser[1].text.split(':', 1)[1].strip()
    else:
        info["note"] = ""
    #Extract video id
    attrs = desc.find('form').attrs
    for attr in attrs:
        if "id" in attr:
            videoID = attrs[attr].split(':', 1)[1].split('}', 1)[0][1:-1]
            break
    #Get show json
    url = "https://www.tagesschau.de/multimedia/video/{}~mediajson.json".format(videoID)
    r = requests.get(url)
    media = json.loads(r.text)
    videoURL = media["_mediaArray"][0]["_mediaStreamArray"][-1]["_stream"]
    #Get subtitles
    subtitleFile = ""
    try:
        subtitleURL = "https://www.tagesschau.de" + media["_subtitleUrl"]
        r = requests.get(subtitleURL)
        rawSubs = r.text
        [subtitles, transcript] = convertSubtitles(rawSubs)
        #Save subtitles
        subtitleFile = os.path.join(directory, "{}_{}.srt".format(show, date))
        with open(subtitleFile, 'w', encoding='utf8') as f:
            f.write(subtitles)
        #Extract presenter
        info["presenter"] = subtitles[:3000].split("Studio:", 1)[1].split('<', 1)[0].strip()
    except KeyError:
        pass
    except IndexError:
        pass
    #Save video
    videoFile = os.path.join(directory, "{}_{}.mp4".format(show, date))
    with requests.get(videoURL, stream=True) as r:
        r.raise_for_status()
        with open(videoFile, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    f.flush()
    #Add meta data
    if os.path.isfile(videoFile):
        writeMetadata(info, videoFile, subtitleFile)
    #Save info file
    infoFile = os.path.join(directory, "{}_{}.json".format(show, date))
    with open(infoFile, 'w', encoding='utf8') as f:
        json.dump(info, f, ensure_ascii=False)
# ########################################################################### #

# --------------------------------------------------------------------------- #
def writeMetadata(info, videoFile, subtitleFile):
    #Add subtitles
    if subtitleFile and os.path.isfile(subtitleFile):
        videoFileComp = os.path.splitext(videoFile)
        tmpFile = videoFileComp[0] + "_tmp" + videoFileComp[1]
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "panic", "-i", videoFile, "-sub_charenc", "UTF-8", "-i", subtitleFile, "-map", "0:v", "-map", "0:a", "-c", "copy", "-map", "1", "-c:s:0", "mov_text", "-metadata:s:s:0", "language=deu", "-metadata:s:a:0", "language=deu", tmpFile]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        process.wait()
        shutil.move(tmpFile, videoFile)
    #Get title and album
    if info["show"] == "ts20":
        album = "tagesschau"
        title = "tagesschau 20:00 Uhr"
    elif info["show"] == "tt":
        album = "tagesthemen"
        title = album
    elif info["show"] == "nm":
        album = "nachtmagazin"
        title = album
    else:
        raise Exception()
    #Clear existing meta data
    cmd = ["exiftool", "-all=", "-overwrite_original", videoFile]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    process.wait()
    #Write metadata
    cmd = ["exiftool"]
    cmd.append("-overwrite_original")
    cmd.append("-Artist=ARD")
    cmd.append("-Album=" + album)
    cmd.append("-Title=" + title)
    cmd.append("-TVShow=" + album)
    cmd.append("-TVNetworkName=Das Erste")
    cmd.append("-Genre=Nonfiction")
    cmd.append("-HDVideo=Yes")
    cmd.append("-MediaType=TV Show")
    if "metadate" in info:
        cmd.append("-ContentCreateDate='{}'".format(info["metadate"]))
    if "topics" in info:
        cmd.append("-LongDescription={}".format(info["topics"]))
    if "note" in info:
        cmd.append("-Comment={}".format(info["note"]))
    cmd.append(videoFile)
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    process.wait()
# ########################################################################### #


# --------------------------------------------------------------------------- #
def convertDate(dateString):
    dt = datetime.strptime(dateString, '%d.%m.%Y %H:%M')
    timezone = pytz.timezone("Europe/Berlin")
    timezoneDate = timezone.localize(dt, is_dst=None)
    timestamp = int(datetime.timestamp(timezoneDate))
    date = timezoneDate.strftime('%Y-%m-%d')
    localtime = datetime.fromtimestamp(timestamp).strftime('%d-%m-%Y %H:%M')
    metadate = timezoneDate.strftime('%Y:%m:%d %H:%M:00 %z')
    metadate = metadate[:-2] + ':' + metadate[-2:]
    return [date, timestamp, localtime, metadate]
# ########################################################################### #

# --------------------------------------------------------------------------- #
def convertSubtitles(subtitles):
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
        items = p.findChildren()
        for item in items:
            if item.name == "span":
                if ("Untertitelung des NDR" in item.text) or ("Copyright Untertitel" in item.text):
                    text = ""
                    textRaw = ""
                    break
                text += "<font color=\"{}\">{}</font>".format(colors[item.attrs["style"]], item.text)
                textRaw += item.text
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
if __name__ == "__main__":
    try:
        archive(sys.argv)
    except KeyboardInterrupt:
        print("Aborted!")
# ########################################################################### #
