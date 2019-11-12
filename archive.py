#!/usr/bin/env python3

# tsarchiver 0.1

import os
import sys
import json
from datetime import datetime
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
            [date, timestamp, localtime] = convertDate(dateString)
            content = page.body.find('div', attrs={'class' : 'inhalt'})
            saveShow("ts20", date, timestamp, localtime, content, directory)
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
        [date, timestamp, localtime] = convertDate(dateString)
        content = page.body.find('div', attrs={'class' : 'inhalt'})
        saveShow("tt", date, timestamp, localtime, content, directory)
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
        [date, timestamp, localtime] = convertDate(dateString)
        content = page.body.find('div', attrs={'class' : 'inhalt'})
        saveShow("nm", date, timestamp, localtime, content, directory)
        last['nm'] = i
# ########################################################################### #

# --------------------------------------------------------------------------- #
# Download show and parse show info
def saveShow(show, date, timestamp, localtime, desc, directory):
    #Print status
    print("Get {} from {}".format(show, localtime))
    #Initialize info json
    info = {}
    teaser = desc.find_all('p', attrs={'class' : 'teasertext'})
    #Extract topics
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
    try:
        subtitleURL = "https://www.tagesschau.de" + media["_subtitleUrl"]
        r = requests.get(subtitleURL)
        subtitles = r.text
        #Save subtitles
        subtitleFile = os.path.join(directory, "{}_{}.xml".format(show, date))
        with open(subtitleFile, 'w', encoding='utf8') as f:
            f.write(subtitles)
    except KeyError:
        pass
    #Extract presenter
    try:
        info["presenter"] = subtitles[:3000].split("Studio:", 1)[1].split('<', 1)[0].strip()
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
    #Save info file
    info["timestamp"] = timestamp
    info["localtime"] = localtime
    infoFile = os.path.join(directory, "{}_{}.json".format(show, date))
    with open(infoFile, 'w', encoding='utf8') as f:
        json.dump(info, f, ensure_ascii=False)
# ########################################################################### #

# --------------------------------------------------------------------------- #
def convertDate(dateString):
    dt = datetime.strptime(dateString, '%d.%m.%Y %H:%M')
    timezone = pytz.timezone("Europe/Berlin")
    timezoneDate = timezone.localize(dt, is_dst=None)
    timestamp = int(datetime.timestamp(timezoneDate))
    localtime = datetime.fromtimestamp(timestamp).strftime('%d-%m-%Y %H:%M')
    return [timezoneDate.strftime('%d-%m-%Y'), timestamp, localtime]
# ########################################################################### #

# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    try:
        archive(sys.argv)
    except KeyboardInterrupt:
        print("Aborted!")
# ########################################################################### #
