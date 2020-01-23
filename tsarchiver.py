#!/usr/bin/env python3
''' tsarchiver - Archive tagesschau, tagesthemen and nachtmagazin '''

import os
import sys
import json
import time
from zipfile import ZipFile, ZIP_DEFLATED
from datetime import datetime
import subprocess
import shutil
import sqlite3
import hashlib
import pytz
from bs4 import BeautifulSoup
import requests
import subconvert

# --------------------------------------------------------------------------- #
def archive(argv):
    '''Archive tagesschau, tagesthemen and nachtmagazin

    :param argv: The command line arguments given by the user
    :type argv: list
    '''
    #Get directory
    try:
        if argv[1] == '-c':
            checkFile = True
            argv.pop(1)
        else:
            checkFile = False
        directory = os.path.normpath(os.path.abspath(argv[1]))
    except IndexError:
        checkFile = False
        directory = os.getcwd()

    dbFile = os.path.join(directory, "archive.db")
    if os.path.isfile(dbFile):
        #Database found, connect to it
        try:
            dbCon = connectDB(dbFile)
            print("Verifying database")
            if not checkDB(dbCon):
                print("Database integrity error!")
                return
            print("Backing up database")
            if not backupDB(dbCon, directory):
                print("Backup failed!")
                return
            db = dbCon.cursor()
            last = getLast(db)
        except sqlite3.Error as e:
            print(e)
            return
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
        try:
            dbCon = createDB(dbFile)
            db = dbCon.cursor()
        except sqlite3.Error as e:
            print(e)
            return
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
    getShows(directory, last, db, checkFile)

    #Close db
    closeDB(dbCon)
# ########################################################################### #

# --------------------------------------------------------------------------- #
def getShows(directory, last, db, checkFile):
    '''Download the new episodes of all shows

    :param directory: The path of the directory in which to save the shows
    :type directory: string
    :param last: The page IDs of the last archived episode for each show
    :type last: dictionary
    :param db: Connection to the metadata database
    :type db: sqlite3.Cursor
    :param checkFile: Whether to perform an integrity check on the file
    :type checkFile: boolean
    '''
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
            content = page.body.find('div', attrs={'class' : 'inhalt'})
            saveShow("ts20", dateString, content, directory, i, db, checkFile)
            last['ts'] = i
    #Get Tagesthemen
    for i in range(last['tt']+2, last['tt']+20, 2):
        url = "https://www.tagesschau.de/multimedia/sendung/tt-{}.html".format(i)
        r = requests.get(url, allow_redirects=False)
        if r.status_code in [404, 301]:
            continue
        page = BeautifulSoup(r.text, features="html.parser")
        title = page.title.text
        if "extra" in title:
            dateString = title.split("extra", 1)[1].split("Uhr", 1)[0].strip()
        else:
            dateString = title.split("tagesthemen", 1)[1].split("Uhr", 1)[0].strip()
        content = page.body.find('div', attrs={'class' : 'inhalt'})
        saveShow("tt", dateString, content, directory, i, db, checkFile)
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
        content = page.body.find('div', attrs={'class' : 'inhalt'})
        saveShow("nm", dateString, content, directory, i, db, checkFile)
        last['nm'] = i
# ########################################################################### #

# --------------------------------------------------------------------------- #
def saveShow(show, dateString, desc, directory, articleID, db, checkFile):
    '''Download an episode of a show, parse the metadata and save them to the database

    :param show: identifier of the show (e.g. 'ts20' for main tagesschau)
    :type show: string
    :param dateString: Air date and time in the form DD.MM.YYYY HH:MM
    :type dateString: string
    :param desc: Episode description
    :type desc: string
    :param articleID: Page ID of the episode
    :type articleID: integer
    :param db: Connection to the metadata database
    :type db: sqlite3.Cursor
    :param checkFile: Whether to perform an integrity check on the file
    :type checkFile: boolean
    '''
    #Convert date
    [date, timestamp, localtime, metadate] = convertDate(dateString)
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
    i = 1
    #Check if file already exists
    while checkFilename(info["videoName"], db):
        i += 1
        info["videoName"] = "{}_{}_{}.mp4".format(show, date, i)
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
    #Check file integrity
    if checkFile:
        cmd = ["ffmpeg", "-v", "error", "-i", videoFile, "-f", "null", "-"]
        out, _ = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).communicate()
        if out:
            print("ERROR: File \"{}\" corrupt!".format(videoFile))
        else:
            print("File \"{}\" check passed".format(videoFile))
    #Calculate checksum
    sha256 = hashlib.sha256()
    with open(videoFile, "rb") as vf:
        for chunk in iter(lambda: vf.read(4096), b""):
            sha256.update(chunk)
    info["checksum"] = sha256.hexdigest()
    #Write info
    saveToDB(db, info, rawSubs, transcript, subtitles)
# ########################################################################### #

# --------------------------------------------------------------------------- #
def writeMetadata(info, videoFile, subtitles):
    '''Write the metadata into the video file

    :param info: All the metadate for an episode
    :type info: dictionary
    :param videoFile: Path of the video file
    :type videoFile: string
    :param subtitles: Subtitles in the SRT format
    :type subtitles: string
    '''
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
    '''Write the metadata to the database

    :param db: Connection to the metadata database
    :type db: sqlite3.Cursor
    :param info: All the metadate for an episode
    :type info: dictionary
    :param raw: Subtitles in the original format
    :type raw: string
    :param trans: Transcript of the video
    :type trans: string
    :param srt: Subtitles in the SRT format
    :type srt: string
    '''
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
        insert = "INSERT INTO videos(datetime, showID, presenterID, subtitleID, topics, note, timstamp, name, articleID, videoID, checksum) VALUES(?,?,?,?,?,?,?,?,?,?,?)"
        if "note" in info and info["note"]:
            note = info["note"]
        else:
            note = None
        if "topics" in info and info["topics"]:
            topics = info["topics"]
        else:
            topics = None
        db.execute(insert, (info["localtime"], showID, presenterID, subID, topics, note, info["timestamp"], info["videoName"], info["articleID"], info["videoID"], info["checksum"]))
    except sqlite3.Error as e:
        print(e)
# ########################################################################### #

# --------------------------------------------------------------------------- #
def idOrInsert(db, table, item, data):
    '''Get the ID of an item in the db table and insert it if it doesn't exist yet

    :param db: Connection to the metadata database
    :type db: sqlite3.Cursor
    :param table: Database table name
    :type table: string
    :param item: Name of the column in which to search
    :type item: string
    :param data: Content of the column which to find (or insert)
    :type data: string

    :returns: ID of the data in the table
    :rtype: integer
    '''
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
    '''Get the article IDs for the last archived episodes from each show

    :param db: Connection to the metadata database
    :type db: sqlite3.Cursor

    :returns: Dict with the show identifier as key and the last article ID as value
    :rtype: dictionary
    '''
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
    '''Convert the date in multiple different formats

    :param dateString: Date and time in the form DD.MM.YYYY HH:MM
    :type directory: string

    :returns: list with four date formats: [YYYY-MM-DD, TIMESTAMP, YYYY-MM-DD HH:MM, YYYY:MM:DD HH:MM:SS OF:FS]
    :rtype: list of strings and int
    '''
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
def checkFilename(name, db):
    '''Check if the given filename is already in the database

    :param name: The filename to check
    :type directory: string
    :param db: Connection to the metadata database
    :type db: sqlite3.Cursor

    :returns: True if filename in database, else False
    :rtype: boolean
    '''
    cmd = "SELECT id FROM videos WHERE name = ?;"
    r = db.execute(cmd, (name,)).fetchone()
    return bool(r)
# ########################################################################### #

# --------------------------------------------------------------------------- #
def connectDB(path):
    '''Connect to a database

    :param path: The path of the database
    :type path: string

    :raises: :class:``sqlite3.Error: Unable to connect to database

    :returns: Connection to the database
    :rtype: sqlite3.Connection
    '''
    #Connect database
    dbCon = sqlite3.connect(path)
    #Return database connection
    return dbCon
# ########################################################################### #

# --------------------------------------------------------------------------- #
def backupDB(con, directory):
    '''Create a backup copy of the database in the 'backups' subdirectory

    :param con: Connection to the database
    :type con: sqlite3.Connection
    :param directory: Path of the directory in which to store the 'backups' subdirectory with the backups
    :type directory: string

    :raises: :class:``sqlite3.Error: Unable to backup database

    :returns: True if backup successful, otherwise False
    :rtype: boolean
    '''
    timestamp = int(time.time())
    backupDir = os.path.join(directory, "backups")
    #Create backup dir if it doesn't already exist
    try:
        os.makedirs(backupDir)
    except OSError:
        pass
    #Create db backup
    backupPath = os.path.join(backupDir, "{}.db".format(timestamp))
    bck = sqlite3.connect(backupPath)
    con.backup(bck)
    bck.close()
    #Zip backup
    with ZipFile(backupPath + ".zip", 'w') as zipf:
        zipf.write(backupPath, arcname="{}.db".format(timestamp), compress_type=ZIP_DEFLATED)
    #Verify zip
    with ZipFile(backupPath + ".zip", 'r') as zipf:
        if zipf.testzip():
            return False
    #Remove uncompressed backup
    os.remove(backupPath)
    return True
# ########################################################################### #

# --------------------------------------------------------------------------- #
def checkDB(con):
    '''Check integrity of database

    :param con: Connection to the database
    :type con: sqlite3.Connection

    :raises: :class:``sqlite3.Error: Unable to check database

    :returns: True if check passed, otherwise False
    :rtype: boolean
    '''
    r = con.execute("pragma integrity_check;")
    res = r.fetchall()
    try:
        return res[0][0] == "ok"
    except IndexError:
        return False
# ########################################################################### #

# --------------------------------------------------------------------------- #
def closeDB(dbCon):
    '''Close the connection to a database

    :param dbCon: Connection to the database
    :type dbCon: sqlite3.Connection
    '''
    if dbCon:
        dbCon.commit()
        dbCon.close()
# ########################################################################### #

# --------------------------------------------------------------------------- #
def createDB(path):
    '''Create new metadata database with the required tables

    :param path: Path at which to store the new database
    :type path: string

    :returns: Connection to the newly created database
    :rtype: sqlite3.Connection
    '''
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
                       videoID TEXT NOT NULL,
                       checksum TEXT NOT NULL
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
# ########################################################################### #

# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    try:
        archive(sys.argv)
    except KeyboardInterrupt:
        print("Aborted!")
# ########################################################################### #
