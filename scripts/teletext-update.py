#!/usr/bin/env python3
# Update the active service and any ancillary sub-services

import config
import os
import re
import subprocess
import time

# Output from `git pull` that means the clone itself is damaged (e.g. a write to
# a network share was interrupted), rather than a transient network problem.
GIT_DAMAGE_SIGNS = (
    "is empty",
    "corrupt",
    "cannot read existing object",
    "invalid index-pack",
    "unable to read",
    "bad object",
    ".lock': File exists",
)

STALE_LOCK_AGE = 10 * 60 # seconds; updates run every 5 minutes and never overlap

def repairGitClone(path):
    # Service clones are read-only mirrors of upstream, so it is safe to throw
    # away damaged objects, stale locks and any half-applied pull.
    gitdir = os.path.join(path, ".git")
    objectsdir = os.path.join(gitdir, "objects")
    now = time.time()

    for root, dirs, files in os.walk(gitdir):
        looseObjects = os.path.dirname(root) == objectsdir and re.fullmatch("[0-9a-f]{2}", os.path.basename(root))
        for name in files:
            file = os.path.join(root, name)
            try:
                stat = os.stat(file)
            except OSError:
                continue

            emptyObject = looseObjects and stat.st_size == 0
            staleLock = name.endswith(".lock") and now - stat.st_mtime > STALE_LOCK_AGE
            emptyFetchHead = root == gitdir and name == "FETCH_HEAD" and stat.st_size == 0

            if emptyObject or staleLock or emptyFetchHead:
                os.remove(file)
                print("removed damaged git file "+file)

    process = subprocess.run(["git", "-C", path, "fetch", "origin"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if process.returncode:
        print("git repair fetch failed with: "+process.stdout.decode("utf8"))
        return

    process = subprocess.run(["git", "-C", path, "reset", "--hard", "@{upstream}"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if process.returncode:
        print("git repair reset failed with: "+process.stdout.decode("utf8"))
    else:
        print("git repair succeeded: "+process.stdout.decode("utf8").strip())

try:
    service = config.getSelectedService()
except Exception as e:
    print(e)
    quit()

def updateService(service):
    # update the service
    if service["type"] == "svn":
        process = subprocess.run(["svn", "up", service["path"]], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        
        if process.returncode:
            print("svn update failed with: "+process.stdout.decode("utf8"))
        
        process = subprocess.run(["svn", "cleanup", service["path"]], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if process.returncode:
            print("svn cleanup failed with: "+process.stdout.decode("utf8"))
        
        
    elif service["type"] == "git":
        process = subprocess.run(["git", "-C", service["path"], "pull"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        
        if process.returncode:
            output = process.stdout.decode("utf8")
            print("git pull failed with: "+output)

            if any(sign in output for sign in GIT_DAMAGE_SIGNS):
                print("git clone at "+service["path"]+" looks damaged; repairing")
                repairGitClone(service["path"])

    subservices = service.get("subservices")
    if subservices:
        for subservice in subservices:
            updateService(subservice) # recurse into subservices

updateService(service)

