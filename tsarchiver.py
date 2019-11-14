#!/usr/bin/env python3

# tsarchiver 1.0

import os
import sys
import json
from datetime import datetime
import subprocess
import shutil
import sqlite3
import pytz
from bs4 import BeautifulSoup
import requests
import subconvert

# --------------------------------------------------------------------------- #
# Archive a news site
def archive(argv):
    #Get directory
    if len(argv) > 1:
        directory = argv[1]
    else:
        directory = os.getcwd()

    dbFile = os.path.join(directory, "archive.db")
    if os.path.isfile(dbFile):
        #Database found, connect to it
        dbCon = connectDB(dbFile)
        db = dbCon.cursor()
        last = getLast(db)
    else:
        #No database found, ask to create one
        while True:
            q = input("No archive database in directory. Create one? [Y|n] ")
            if not q:
                q = 'y'
            a = q[0].lower()
            if a in ['y', 'n']:
                break
        #Should not create database, exiting
        if a != 'y':
            print("Exiting...")
            return
        #Create database
        dbCon = createDB(dbFile)
        db = dbCon.cursor()
        #Ask for page start indexes
        last = {}
        while True:
            try:
                last["ts20"] = int(input("Start archiving from tagesschau page index: "))
                break
            except ValueError:
                print("Invalid input, please enter a number")
        while True:
            try:
                last["tt"] = int(input("Start archiving from tagesthemen page index: "))
                break
            except ValueError:
                print("Invalid input, please enter a number")
        while True:
            try:
                last["nm"] = int(input("Start archiving from nachtmagazin page index: "))
                break
            except ValueError:
                print("Invalid input, please enter a number")

    #Get shows
    getShows(directory, last, db)

    #Close db
    closeDB(dbCon)
# ########################################################################### #

# --------------------------------------------------------------------------- #
# Get the info for the new shows and update the last ID
def getShows(directory, last, db):
    #Get Tagesschau
    for i in range(last['ts20']+2, last['ts20']+80, 2):
        url = "https://www.tagesschau.de/multimedia/sendung/ts-{}.html".format(i)
        r = requests.get(url, allow_redirects=False)
        if r.status_code in [404, 301]:
            continue
        page = BeautifulSoup(r.text, features="html.parser")
        title = page.title.text
        if "20:00" in title:
            dateString = title.split("tagesschau", 1)[1].split("Uhr", 1)[0].strip()
            [date, timestamp, localtime, metadate] = convertDate(dateString)
            content = page.body.find('div', attrs={'class' : 'inhalt'})
            saveShow("ts20", date, timestamp, localtime, metadate, content, directory, i, db)
            last['ts'] = i
    #Get Tagesthemen
    for i in range(last['tt']+2, last['tt']+20, 2):
        url = "https://www.tagesschau.de/multimedia/sendung/tt-{}.html".format(i)
        r = requests.get(url, allow_redirects=False)
        if r.status_code in [404, 301]:
            continue
        page = BeautifulSoup(r.text, features="html.parser")
        title = page.title.text
        dateString = title.split("tagesthemen", 1)[1].split("Uhr", 1)[0].strip()
        [date, timestamp, localtime, metadate] = convertDate(dateString)
        content = page.body.find('div', attrs={'class' : 'inhalt'})
        saveShow("tt", date, timestamp, localtime, metadate, content, directory, i, db)
        last['tt'] = i
    #Get Nachtmagazin
    for i in range(last['nm']+2, last['nm']+8, 2):
        url = "https://www.tagesschau.de/multimedia/sendung/nm-{}.html".format(i)
        r = requests.get(url, allow_redirects=False)
        if r.status_code in [404, 301]:
            continue
        page = BeautifulSoup(r.text, features="html.parser")
        title = page.title.text
        dateString = title.split("nachtmagazin", 1)[1].split("Uhr", 1)[0].strip()
        [date, timestamp, localtime, metadate] = convertDate(dateString)
        content = page.body.find('div', attrs={'class' : 'inhalt'})
        saveShow("nm", date, timestamp, localtime, metadate, content, directory, i, db)
        last['nm'] = i
# ########################################################################### #

# --------------------------------------------------------------------------- #
# Download show and parse show info
def saveShow(show, date, timestamp, localtime, metadate, desc, directory, articleID, db):
    #Print status
    print("Get {} from {} ({})".format(show, localtime, articleID))
    #Initialize info json
    info = {}
    info["show"] = show
    info["timestamp"] = timestamp
    info["localtime"] = localtime
    info["metadate"] = metadate
    info["articleID"] = articleID
    #Extract topics
    teaser = desc.find_all('p', attrs={'class' : 'teasertext'})
    info["topics"] = teaser[0].text.split(':', 1)[1].strip()
    #Extract notes
    if "Hinweis" in teaser[1].text:
        info["note"] = teaser[1].text.split(':', 1)[1].strip()
    #Extract video id
    attrs = desc.find('form').attrs
    for attr in attrs:
        if "id" in attr:
            info["videoID"] = attrs[attr].split(':', 1)[1].split('}', 1)[0][1:-1]
            break
    #Get show json
    url = "https://www.tagesschau.de/multimedia/video/{}~mediajson.json".format(info["videoID"])
    r = requests.get(url)
    media = json.loads(r.text)
    videoURL = media["_mediaArray"][0]["_mediaStreamArray"][-1]["_stream"]
    #Get subtitles
    rawSubs = ""
    subtitles = ""
    transcript = ""
    try:
        subtitleURL = "https://www.tagesschau.de" + media["_subtitleUrl"]
        r = requests.get(subtitleURL)
        rawSubs = r.text
        [subtitles, transcript] = subconvert.convertEBU(rawSubs)
        #Extract presenter
        info["presenter"] = subtitles[:3000].split("Studio:", 1)[1].split('<', 1)[0].strip()
    except KeyError:
        pass
    except IndexError:
        pass
    #Save video
    info["videoName"] = "{}_{}.mp4".format(show, date)
    videoFile = os.path.join(directory, info["videoName"])
    with requests.get(videoURL, stream=True) as r:
        r.raise_for_status()
        with open(videoFile, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    f.flush()
    #Add meta data
    if os.path.isfile(videoFile):
        writeMetadata(info, videoFile, subtitles)
    #Write info
    saveToDB(db, info, rawSubs, transcript, subtitles)
# ########################################################################### #

# --------------------------------------------------------------------------- #
def writeMetadata(info, videoFile, subtitles):
    #Add subtitles
    if subtitles:
        #Tmp file path
        videoFileComp = os.path.splitext(videoFile)
        tmpFile = videoFileComp[0] + "_tmp" + videoFileComp[1]
        #Save subtitles
        subtitleFile = videoFileComp[0] + ".srt"
        with open(subtitleFile, 'w', encoding='utf8') as f:
            f.write(subtitles)
        #Add subtitle to video using ffmpeg
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "panic", "-i", videoFile, "-sub_charenc", "UTF-8", "-i", subtitleFile, "-map", "0:v", "-map", "0:a", "-c", "copy", "-map", "1", "-c:s:0", "mov_text", "-metadata:s:s:0", "language=deu", "-metadata:s:a:0", "language=deu", tmpFile]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        process.wait()
        shutil.move(tmpFile, videoFile)
        os.remove(subtitleFile)
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
def saveToDB(db, info, raw, trans, srt):
    try:
        #Check/insert show
        showID = idOrInsert(db, "shows", "name", info["show"])
        if "presenter" in info and info["presenter"]:
            #Check/insert presenter
            presenterID = idOrInsert(db, "presenters", "name", info["presenter"])
        else:
            presenterID = None
        if raw:
            #Insert subtitles
            insert = "INSERT INTO subtitles(raw, transcript, srt) VALUES(?,?,?)"
            db.execute(insert, (raw, trans, srt))
            subID = db.lastrowid
        else:
            subID = None
        #Insert video info
        insert = "INSERT INTO videos(datetime, showID, presenterID, subtitleID, topics, note, timstamp, name, articleID, videoID) VALUES(?,?,?,?,?,?,?,?,?,?)"
        if "note" in info and info["note"]:
            note = info["note"]
        else:
            note = None
        if "topics" in info and info["topics"]:
            topics = info["topics"]
        else:
            topics = None
        db.execute(insert, (info["localtime"], showID, presenterID, subID, topics, note, info["timestamp"], info["videoName"], info["articleID"], info["videoID"]))
    except sqlite3.Error as e:
        print(e)
# ########################################################################### #

# --------------------------------------------------------------------------- #
def idOrInsert(db, table, item, data):
    cmd = "SELECT id FROM {} WHERE {} = '{}'".format(table, item, data)
    r = db.execute(cmd).fetchone()
    if not r:
        insert = "INSERT INTO {}({}) VALUES(?)".format(table, item)
        db.execute(insert, (data,))
        r = [db.lastrowid]
    return r[0]
# ########################################################################### #

# --------------------------------------------------------------------------- #
def getLast(db):
    last = {}
    cmd = "SELECT MAX(articleID) FROM videos INNER JOIN shows ON shows.id = videos.showID WHERE shows.name=?"
    r = db.execute(cmd, ("ts20",)).fetchone()
    if not r[0]:
        while True:
            try:
                print("No tagesschau archived yet")
                last["ts20"] = int(input("Start archiving from tagesschau page index: "))
                break
            except ValueError:
                print("Invalid input, please enter a number")
    else:
        last["ts20"] = r[0]
    r = db.execute(cmd, ("tt",)).fetchone()
    if not r[0]:
        while True:
            try:
                print("No tagesthemen archived yet")
                last["tt"] = int(input("Start archiving from tagesthemen page index: "))
                break
            except ValueError:
                print("Invalid input, please enter a number")
    else:
        last["tt"] = r[0]
    r = db.execute(cmd, ("nm",)).fetchone()
    if not r[0]:
        while True:
            try:
                print("No nachtmagazin archived yet")
                last["nm"] = int(input("Start archiving from nachtmagazin page index: "))
                break
            except ValueError:
                print("Invalid input, please enter a number")
    else:
        last["nm"] = r[0]

    return last
# ########################################################################### #

# --------------------------------------------------------------------------- #
def convertDate(dateString):
    dt = datetime.strptime(dateString, '%d.%m.%Y %H:%M')
    timezone = pytz.timezone("Europe/Berlin")
    timezoneDate = timezone.localize(dt, is_dst=None)
    timestamp = int(datetime.timestamp(timezoneDate))
    date = timezoneDate.strftime('%Y-%m-%d')
    localtime = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M')
    metadate = timezoneDate.strftime('%Y:%m:%d %H:%M:00 %z')
    metadate = metadate[:-2] + ':' + metadate[-2:]
    return [date, timestamp, localtime, metadate]
# ########################################################################### #


# --------------------------------------------------------------------------- #
def connectDB(path):
    try:
        #Connect database
        dbCon = sqlite3.connect(path)
        #Return database connection
        return dbCon
    except sqlite3.Error as e:
        print(e)
# ########################################################################### #

# --------------------------------------------------------------------------- #
def closeDB(dbCon):
    if dbCon:
        dbCon.commit()
        dbCon.close()
# ########################################################################### #

# --------------------------------------------------------------------------- #
def createDB(path):
    videoCmd = """ CREATE TABLE IF NOT EXISTS videos (
                       id INTEGER PRIMARY KEY AUTOINCREMENT UNIQUE NOT NULL,
                       datetime TEXT NOT NULL,
                       showID INTEGER NOT NULL,
                       presenterID INTEGER,
                       subtitleID INTEGER,
                       topics TEXT,
                       note TEXT,
                       timstamp INTEGER NOT NULL,
                       name TEXT NOT NULL,
                       articleID INTEGER NOT NULL,
                       videoID TEXT NOT NULL
                   ); """
    subtitleCmd = """ CREATE TABLE IF NOT EXISTS subtitles (
                          id INTEGER PRIMARY KEY AUTOINCREMENT UNIQUE NOT NULL,
                          raw TEXT NOT NULL,
                          transcript TEXT NOT NULL,
                          srt TEXT NOT NULL
                      ); """
    presenterCmd = """ CREATE TABLE IF NOT EXISTS presenters (
                           id INTEGER PRIMARY KEY AUTOINCREMENT UNIQUE NOT NULL,
                           name TEXT NOT NULL
                       ); """
    showCmd = """ CREATE TABLE IF NOT EXISTS shows (
                      id INTEGER PRIMARY KEY AUTOINCREMENT UNIQUE NOT NULL,
                      name TEXT NOT NULL
                  ); """
    conn = None
    try:
        #Create database
        dbCon = connectDB(path)
        db = dbCon.cursor()
        #Set encoding
        db.execute("pragma encoding=UTF8")
        #Create tables
        db.execute(videoCmd)
        db.execute(showCmd)
        db.execute(presenterCmd)
        db.execute(subtitleCmd)
        #Return database connection
        return dbCon
    except sqlite3.Error as e:
        print(e)
        closeDB(dbCon)
# ########################################################################### #

# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    try:
        archive(sys.argv)
    except KeyboardInterrupt:
        print("Aborted!")
# ########################################################################### #
