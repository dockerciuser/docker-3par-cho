# Reliability Test Script for HPE 3Par Docker Volume plugin
#
#      randomly performs:  volume creation, deletion, mount, unmount
#       for a duration of time.
#
#       Prerequisites:
#           - a running Docker engine
#           - Docker SDK
#           - Python Packages
#           - HPE 3Par Docker Volume plugin in enabled state

import argparse
import os
from os import sys
import random
# import threading
import logging
import time
# import datetime
from time import time
from time import sleep
from datetime import timedelta
import httplib2
import json
# import pprint
import commands
import unittest

import docker
from docker.utils import kwargs_from_env
import six


# Test global variables
logger = None

totalActions = 0
totalActions_create = 0
totalActions_delete = 0
totalActions_creates = 0
totalActions_deletes = 0
totalActions_mount = 0
totalActions_unmount = 0

totalErrors = 0
totalErrors_create = 0
totalErrors_delete = 0
totalErrors_creates = 0
totalErrors_deletes = 0
totalErrors_mount = 0
totalErrors_unmount = 0

clock_start = time()
WebServiceLogger = None

volumeCount=0

waitTimeInMinutes = 5

parser = argparse.ArgumentParser()
parser.add_argument("-maxVolumes")
parser.add_argument("-maxVolumeSize", default=10)
parser.add_argument("-duration")
parser.add_argument("-userAgent", default="DockerChoTest")
parser.add_argument("-logfile", default=("./DockerChoTest-%d.log" % time()))
args = parser.parse_args()

def prompt_for_arg(arg, field, prompt, default):
    if getattr(arg, field) is None:
        try:
            r = raw_input(prompt)
            if len(r) > 0:
                setattr(arg, field, r)
            else:
                setattr(arg, field, default)
        except:
            print "Aborted."
            sys.exit()

prompt_for_arg(args, "maxVolumes", "Max number of volumes to create (8): ", "8")
prompt_for_arg(args, "duration", "Test duration in minutes (1): ", "1")
print

args.duration = int(args.duration)
args.maxVolumes = int(args.maxVolumes)
args.maxVolumeSize = int(args.maxVolumeSize)

#######################################################

##### Logging Functions ######################################
def SetupLogging(logfile=None):
    # create logger
    global logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # create console handler and set level to debug
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)

    # create formatter
    formatter = logging.Formatter('%(asctime)s%(message)s', datefmt="[%Y-%m-%d][%H:%M:%S]")

    # add formatter to ch
    ch.setFormatter(formatter)

    # add ch to logger
    logger.addHandler(ch)

    # also log to a file given on command line
    if logfile:
        ch = logging.FileHandler(logfile,"w")
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(formatter)
        logger.addHandler(ch)


def LogMessage(msg="",actionIncrement=0,action=None):
    global totalActions
    global totalActions_create
    global totalActions_delete
    global totalActions_creates
    global totalActions_deletes
    global totalActions_mount
    global totalActions_unmount

    totalActions += actionIncrement

    entry = "[A:%d,E:%d] %s" % (totalActions, totalErrors, msg)

    logger.info(entry)

    if action and action == "create_volume":
        totalActions_create += actionIncrement
    elif action and action == "delete_volume":
        totalActions_delete += actionIncrement
    elif action and action == "mount_volume":
        totalActions_mount += actionIncrement
    elif action and action == "unmount_volume":
        totalActions_unmount += actionIncrement

    if msg == "break out wait after 15 minutes...":
        dump = commands.getstatusoutput('top -bn1')
        entry = "[A:%d,E:%d] %s" % (totalActions, totalErrors, dump)
        logger.info(entry)

def LogError(msg="", errorIncrement=1, action=None):
    global totalErrors
    global totalErrors_create
    global totalErrors_delete
    global totalErrors_creates
    global totalErrors_deletes
    global totalErrors_mount
    global totalErrors_unmount

    totalErrors += errorIncrement

    entry = "[A:%d,E:%d] ERROR >>>>>> %s" % (totalActions, totalErrors, msg)
    logger.info(entry)

    if action and action == "create_volume":
        totalErrors_create += errorIncrement
    elif action and action == "delete_volume":
        totalErrors_delete += errorIncrement
    elif action and action == "mount_volume":
        totalErrors_mount += errorIncrement
    elif action and action == "unmount_volume":
        totalErrors_unmount += errorIncrement

def TestFinished():
    global clock_start
    LogMessage( "Test performed %s actions." % totalActions)
    LogMessage( "Test performed %s create volume actions." % totalActions_create)
    LogMessage( "Test performed %s delete volume actions." % totalActions_delete)
    LogMessage( "Test performed %s mount volume actions." % totalActions_mount)
    LogMessage( "Test performed %s unmount volume actions." % totalActions_unmount)

    LogMessage( "Test observed  %s errors." % totalErrors)
    LogMessage( "Test observed  %s create volume errors." % totalErrors_create)
    LogMessage( "Test observed  %s delete volume errors." % totalErrors_delete)
    LogMessage( "Test observed  %s mount volume errors." % totalErrors_mount)
    LogMessage( "Test observed  %s unmount volume errors." % totalErrors_unmount)

    LogMessage( "Total test time: %s" % timedelta(seconds=time()-clock_start))
    LogMessage( "Test finished.")

##### Exception Classes ######################################
class TestError:
    def __init__(self, message):
        self.message = message

    def __str__(self):
        return self.message

class WebServiceException:
    """OpenStack web proxy error exception class"""

    def __init__(self, method, url, status, message, text=None):
        self.method = method
        self.url = url
        self.status = status
        self.message = message
        self.text = text

    def __str__(self):
        return "WebServiceException ERROR %s '%s' returned from %s %s\n%s" % (self.status, self.message, self.method, self.url, self.text)

##### OpenStack client class ######################################
class Docker3ParVolumePlugin(unittest.TestCase):
    def createVolume(self, name, driver, **kwargs):
        client = docker.from_env(version=TEST_API_VERSION)
        if 'flash_cache' in kwargs:
            kwargs['flash-cache'] = kwargs.pop('flash_cache')
        # Create a volume
        volume = client.volumes.create(name=name, driver=driver,
                                       driver_opts=kwargs
        )
        assert volume.id
        assert volume.name == name
        assert volume.attrs['Driver'] == driver
        assert volume.attrs['Options'] == kwargs

        get_volume = client.volumes.get(volume.id)
        assert get_volume.name == name

        return volume

    def deleteVolume(self, volume):
        client = docker.from_env(version=TEST_API_VERSION)
        # volume = client.volumes.create('dockerpytest_1')

        assert volume in client.volumes.list()
        assert volume in client.volumes.list(filters={'name': volume.name })
        assert volume not in client.volumes.list(filters={'name': 'foobar'})

        volume.remove()
        assert volume not in client.volumes.list()

    def mountVolume(self):
        if six.PY2:
            self.assertRegex = self.assertRegexpMatches
            self.assertCountEqual = self.assertItemsEqual

        client = docker.from_env(version=TEST_API_VERSION)
        client.volumes.create(name="somevolume")

        container = client.containers.run(
            "alpine", "sh -c 'echo \"hello\" > /insidecontainer/test'",
            volumes=["somevolume:/insidecontainer"],
            detach=True
        )
        container.wait()
        client.containers.

        out = client.containers.run(
            "alpine", "cat /insidecontainer/test",
            volumes=["somevolume:/insidecontainer"]
        )
        self.assertEqual(out, b'hello\n')


    def unmountVolume(self, serverId, volumeId, mountmentId, wait=True):
        #delay can occur in case when the status of volume selected for unmount is already in "unmounting state".
        #we should wait for unmountment to complete
        content = self.request("GET", "cinder", "/volumes/%s" % volumeId)
        status = content['volume']['status']
        if status == "unmounting":
            return None

        path = "/servers/%s/os-volume_mountments/%s" % (serverId,mountmentId)

        self.request("DELETE", "nova", path)
        content = self.request("GET", "cinder", "/volumes/%s" % volumeId)

        if wait:
            # wait for volume unmount to complete
            wait_start = time()
            done = False
            while not done and (time()  -  wait_start < waitTimeInMinutes * 60):
                content = self.request("GET", "cinder", "/volumes/%s" % volumeId)
                status = content['volume']['status']
                done = (status == "available" or status == "error")

                if((time()  -  wait_start) > waitTimeInMinutes * 60):
                    LogMessage("unmountVolume--break out wait after %s minutes..." % str(waitTimeInMinutes))

                    if status != "available":
                        raise TestError("Failed to unmount volume.  Request: %s" % str(content))

        return content['volume']

    def hardReboot(self, serverId, wait=True):
        path = "/servers/%s/action" % (serverId)
        body = {
                'reboot': {
                               'type': "HARD"
                          }
               }
        self.request("POST", "nova", path, body=body)
        #self.request("POST", "nova", path)

    def getVolumes(self, wait=True):
        content = self.request("GET", "cinder", "/volumes")
        volumes = content['volumes']

        LogMessage(str(volumes))
        LogMessage("len = %s " % len(volumes))

        return True

##### Individual test functions ######################################

def TestGetVolumes():
    ws.getVolumes()
    return True

def TestVolumeCreate(volumes):
    global volumeCount
    name = "vol%d" % volumeCount
    volumeCount += 1
    capacity = random.randint(1,args.maxVolumeSize)
    LogMessage("----->Performing create of new %d GB volume %s" % (capacity,name))
    volume = ws.createVolume(name,("Volume created by %s" % args.userAgent), capacity)
    volumes[volume["id"]] = volume
    return True


def TestVolumemount(servers, volumes):
    global deviceId

    availableVolumeIds = [k for (k,v) in volumes.items() if v["status"] == "available"]
    if len(availableVolumeIds) == 0:
        LogMessage("no available volumes to mount volume")
        return False # no volumes available to mount

    volumeId = random.choice(availableVolumeIds)
    availableServerIds = [k for (k,v) in servers.items() if v == "available"]
    if len(availableServerIds) == 0:
        return False # no servers available to mount to

    serverId = random.choice(availableServerIds)

    LogMessage("----->Performing mount of volume '%s'/%s to server %s" % (volumes[volumeId]["display_name"],volumeId,serverId))
    mountId,volume = ws.mountVolume(serverId, volumeId)
    if mountId is not None and volume is not None:
        servers[serverId] = (mountId,volumeId)
        volumes[volumeId] = volume
    return True


def TestVolumeunmount(servers, volumes):
    mountedServerIds = [k for (k,v) in servers.items() if v != "available"]
    if len(mountedServerIds) == 0:
        LogMessage("no available servers to unmount volume")
        return False # no volumes available to unmount

    serverId = random.choice(mountedServerIds)
    mountId,volumeId = servers[serverId]

    # delay to allow unmount to complete in case want to unmount it
    sleep(5)

    LogMessage("----->Performing unmount of volume '%s'/%s from server %s mounte_id %s" % (volumes[volumeId]["display_name"],volumeId,serverId,mountId))
    volume = ws.unmountVolume(serverId, volumeId, mountId)
    if volume is not None:
            servers[serverId] = "available"
            volumes[volumeId] = volume
    return True


def TestVolumeDelete(volumes):
    LogMessage( "volume len before del = %s " % len(volumes))
    availableVolumeIds = [k for (k,v) in volumes.items() if (v["status"] == "available")]
    if len(availableVolumeIds) == 0:
        LogMessage("no available volumes to delete volume")
        return False # no volumes available to delete

    found = False
    volumeId = None
    volumeId = random.choice(availableVolumeIds)
    LogMessage("----->Performing delete of volume '%s'/%s" % (volumes[volumeId]["display_name"],volumeId))
    ws.deleteVolume(volumeId)
    del volumes[volumeId]

    LogMessage( "volume len after del = %s " % len(volumes))

    return True

#######################################################

SetupLogging(args.logfile)
random.seed()

LogMessage("===============Starting %s Test===================" % os.path.basename(os.sys.argv[0]))
LogMessage("Args: %s" % args)

try:
    ws = OpenStackClient(args.keystoneEndpoint, args.userAgent)

    LogMessage("Contacting keystone for authentication & endpoint discovery...")
    ws.authenticate(args.username, args.password, args.tenant)

    LogMessage("Authentication successful.")
    LogMessage("Contacting nova to get server instances for mount/unmount operations...")
    servers = dict([(s["id"],"available") for s in ws.request("GET", "nova", "/servers")["servers"]])

    if len(servers) == 0:
        LogMessage("!!! No server instances to mount volumes to.  Continuing performing volume create/delete only !!!")
    else:
        LogMessage("mounting volumes to %d available server instances." % len(servers))

    ######################################################
    # define actions and % of time they should be performed (from previous entry to %)
    # create          - 25%
    # mount          - 22%
    # unmount        - 22%
    # delete          - 11%
    actions = [("create_volume", 25),("mount_volume",57),("unmount_volume",79),("delete_volume",100)]
    volumes = {}

    action = None

    hour_start = time()

    while (time() - clock_start) < int(args.duration) * 60:

        #reauthenticate around 30 minutes
        if (time() - hour_start ) > (30 * 60):
            LogMessage("re-authenticate after 30 minutes")
            ws.authenticate(args.username, args.password, args.tenant)
            hour_start = time()


        num = random.randint(1,100)
        action = [action for (action,value) in actions if num <= value][0]

        try:
            if action == "create_volume":
                if len(volumes) >= args.maxVolumes - 1:
                    continue

                performed_action = TestVolumeCreate(volumes)
                if performed_action:
                    LogMessage("Successfully completed %s operation." % action,1,action)
            elif action == "mount_volume":
                performed_action = TestVolumemount(servers, volumes)
                if performed_action:
                    LogMessage("Successfully completed %s operation." % action,1,action)

            elif action == "unmount_volume":
                performed_action = TestVolumeunmount(servers, volumes)
                if performed_action:
                    LogMessage("Successfully completed %s operation." % action,1,action)

            elif action == "delete_volume":
                performed_action = TestVolumeDelete(volumes)
                if performed_action:
                    LogMessage("Successfully completed %s operation." % action,1,action)

            else:
                LogError("Unknown test action '%s'" % action)
                break


        except TestError as e:
            LogError(str(e), 1, action)
            continue
        except WebServiceException as e:
            LogError(str(e), 1, action)
            continue

    #clean up
    LogMessage("cleanup...")
    while len(volumes) > 0:
        try:
            action = "unmount_volume"
            performed_action = TestVolumeunmount(servers,volumes)
            if performed_action:
                LogMessage("Successfully completed unmount Volume in clean up.", 1, "unmount_volume")

            action = "delete_volume"
            performed_action = TestVolumeDelete(volumes)
            if performed_action:
                LogMessage("Successfully completed delete volume in clean up." , 1, "delete_volume")

        except TestError as e:
            LogError(str(e), 1, action)
            break
        except WebServiceException as e:
            LogError(str(e), 1, action)
            break


except TestError as e:
    LogError(str(e))
    LogError("Aborting test.  Too frightened to continue.",0)
except WebServiceException as e:
    LogError(str(e))
    LogError("Aborting test.  Too frightened to continue.",0)

############################################
LogMessage("=========================================")
TestFinished()
LogMessage("Finished.")
