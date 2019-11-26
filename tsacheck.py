#!/usr/bin/env python3
''' tsacheck - Check intregrity of downloaded files '''

import sys
import os
import sqlite3
import subprocess
import hashlib

# --------------------------------------------------------------------------- #
def check(argv):
    '''Check integrity of downloaded files

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

    dbPath = os.path.join(directory, "archive.db")
    if not os.path.isfile(dbPath):
        print("ERROR: No archive database found!")
        return
    try:
        #Connect to database
        db = connectDB(dbPath)
        r = db.execute("SELECT id,name,checksum FROM videos;")
        for item in r.fetchall():
            filePath = os.path.join(directory, item[1])
            #Check if file exists
            if not os.path.isfile(filePath):
                print("ERROR: File {} not found".format(item[1]))
                continue
            #Check file integrity
            if checkFile:
                cmd = ["ffmpeg", "-v", "error", "-i", filePath, "-f", "null", "-"]
                out, _ = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).communicate()
                if out:
                    print("ERROR: File \"{}\" corrupt!".format(item[1]))
                else:
                    print("File \"{}\" check passed".format(item[1]))
            #Calculate checksum
            sha256 = hashlib.sha256()
            with open(filePath, "rb") as vf:
                for chunk in iter(lambda: vf.read(4096), b""):
                    sha256.update(chunk)
            checksum = sha256.hexdigest()
            if item[2]:
                #Compare checksums
                if checksum == item[2]:
                    print("File \"{}\" checksums match".format(item[1]))
                else:
                    print("ERROR: File \"{}\" checksums mismatch".format(item[1]))
            else:
                print("File \"{}\" no checksum saved yet".format(item[1]))
                db.execute("UPDATE videos SET checksum = ? WHERE id = ?;", (checksum, item[0]))
        #Close database
        closeDB(db)
    except sqlite3.Error as e:
        print("ERROR: " + e)
        return
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
def closeDB(dbCon):
    '''Close the connection to a database

    :param dbCon: Connection to the database
    :type dbCon: sqlite3.Connection

    :raises: :class:``sqlite3.Error: Unable to close database
    '''
    if dbCon:
        dbCon.commit()
        dbCon.close()
# ########################################################################### #

# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    try:
        check(sys.argv)
    except KeyboardInterrupt:
        print("Aborted!")
# ########################################################################### #
