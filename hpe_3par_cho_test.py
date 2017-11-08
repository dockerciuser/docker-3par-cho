####################################################################
# Reliability Test Script for HPE 3Par Docker Volume plugin
#
#      randomly performs:  volume creation, deletion, mount and unmount
#      for a duration of time.
#
#       Prerequisites:
#           - a running Docker engine
#           - Docker SDK
#           - Python Packages
#           - HPE 3Par Docker Volume plugin in enabled state
######################################################################

import argparse
import os
from os import sys
import random
import logging
import time
from time import time
from datetime import timedelta
import commands
import docker


# Test global variables

BUSYBOX = 'busybox:buildroot-2014.02'
TEST_API_VERSION = os.environ.get('DOCKER_TEST_API_VERSION')

logger = None

totalActions = 0
totalActions_create = 0
totalActions_delete = 0
totalActions_mount_unmount = 0

totalErrors = 0
totalErrors_create = 0
totalErrors_delete = 0
totalErrors_mount_unmount = 0

clock_start = time()

volumeCount=0

waitTimeInMinutes = 5

parser = argparse.ArgumentParser()
parser.add_argument("-maxVolumes")
parser.add_argument("-maxVolumeSize", default=10)
parser.add_argument("-duration")
parser.add_argument("-plugin")
parser.add_argument("-etcd")
parser.add_argument("-provisioning")
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
prompt_for_arg(args, "plugin", "Name of the plugin repository with version (hpe:latest): ", "hpe:latest")
prompt_for_arg(args, "provisioning", "Provisioning type of volumes (thin, full or dedup): ", "thin")
prompt_for_arg(args, "etcd", "Name of the etcd container (etcd): ", "etcd")
print

args.duration = int(args.duration)
args.maxVolumes = int(args.maxVolumes)
args.maxVolumeSize = int(args.maxVolumeSize)
HPE3PAR = args.plugin
PROVISIONING = args.provisioning
ETCD_CONTAINER = args.etcd


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

# Method for message logger and count the number of operations performed during the test
def LogMessage(msg="",actionIncrement=0,action=None):
    global totalActions
    global totalActions_create
    global totalActions_delete
    global totalActions_mount_unmount

    totalActions += actionIncrement

    entry = "[A:%d,E:%d] %s" % (totalActions, totalErrors, msg)

    logger.info(entry)

    if action and action == "create_volume":
        totalActions_create += actionIncrement
    elif action and action == "delete_volume":
        totalActions_delete += actionIncrement
    elif action and action == "mount_unmount_volume":
        totalActions_mount_unmount += actionIncrement

    if msg == "break out wait after 15 minutes...":
        dump = commands.getstatusoutput('top -bn1')
        entry = "[A:%d,E:%d] %s" % (totalActions, totalErrors, dump)
        logger.info(entry)

# Method for error logger and count the number of errors occurred during the tests
def LogError(msg="", errorIncrement=1, action=None):
    global totalErrors
    global totalErrors_create
    global totalErrors_delete
    global totalErrors_mount_unmount

    totalErrors += errorIncrement

    entry = "[A:%d,E:%d] ERROR >>>>>> %s" % (totalActions, totalErrors, msg)
    logger.info(entry)

    if action and action == "create_volume":
        totalErrors_create += errorIncrement
    elif action and action == "delete_volume":
        totalErrors_delete += errorIncrement
    elif action and action == "mount_unmount_volume":
        totalErrors_mount_unmount += errorIncrement

# Method for logging test results and test time after performing the different actions
def TestFinished():
    global clock_start
    LogMessage( "Test performed %s actions." % totalActions)
    LogMessage( "Test performed %s create volume actions." % totalActions_create)
    LogMessage( "Test performed %s delete volume actions." % totalActions_delete)
    LogMessage( "Test performed %s mount and unmount volume actions." % totalActions_mount_unmount)

    LogMessage( "Test observed  %s errors." % totalErrors)
    LogMessage( "Test observed  %s create volume errors." % totalErrors_create)
    LogMessage( "Test observed  %s delete volume errors." % totalErrors_delete)
    LogMessage( "Test observed  %s mount and unmount volume errors." % totalErrors_mount_unmount)


    LogMessage( "Total test time: %s" % timedelta(seconds=time()-clock_start))
    LogMessage( "Test finished.")

##### Exception Classes ######################################
class TestError:
    def __init__(self, message):
        self.message = message

    def __str__(self):
        return self.message

##### Docker Volume Plugin class ######################################
class Docker3ParVolumePlugin():
    # method to perform create volume operation
    def create_volume(self, name, driver, **kwargs):
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

    # method to perform delete volume operation
    def delete_volume(self, volume):
        client = docker.from_env(version=TEST_API_VERSION)
        volume.remove()
        assert volume not in client.volumes.list()
        return True

    # method to perform mount and unmount operation and delete containers after performing operations
    def mount_unmount_volume(self, volume):
        client = docker.from_env(version=TEST_API_VERSION)
        container = client.containers.run(BUSYBOX, "sh", detach=True,
                                          tty=True, stdin_open=True,
                                          volumes=[volume.name + ':/insidecontainer']
        )
        container.exec_run("sh -c 'echo \"data\" > /insidecontainer/test'")
        assert container.exec_run("cat /insidecontainer/test") == b"data\n"
        container.stop()
        container.wait()
        container.remove()
        return True

##### Individual test functions ######################################

def test_create_volume():
    global volumeCount
    name = "volume-%d" % volumeCount
    volumeCount += 1
    capacity = random.randint(1,args.maxVolumeSize)
    LogMessage("==========> Performing create of new %d GB volume: %s <==========" % (capacity,name))
    volume = dcv.create_volume(name, driver=HPE3PAR,
                               size=str(capacity), provisioning=PROVISIONING)
    return volume

#######################################################

# This part will perform create_volume, mount_unmount_volume and delete_volume
# operations randomly till the time in minutes passed as duration during running this test.

SetupLogging(args.logfile)
random.seed()

LogMessage("=====================STARTING %s TESTS===================" % os.path.basename(os.sys.argv[0]))
LogMessage("Args: %s" % args)


try:
    client = docker.from_env(version=TEST_API_VERSION)
    dcv = Docker3ParVolumePlugin()

    actions = [("create_volume", 25),("mount_unmount_volume", 57),("delete_volume",100)]
    volumes = []
    volume_list = []
    container_list = []
    action = None
    hour_start = time()

    while (time() - clock_start) < int(args.duration) * 60:

        num = random.randint(1, 100)
        action = [action for (action, value) in actions if num <= value][0]

        try:
            if action == "create_volume":
                if len(volumes) >= args.maxVolumes - 1:
                    continue
                performed_action= test_create_volume()
                if performed_action:
                    LogMessage("************Successfully completed %s operation.**************" % action,1,action)

            elif action == "mount_unmount_volume":
                volumes = client.volumes.list(filters = {'dangling':True})
                if len(volumes) > 0:
                    LogMessage("==========> Performing mount and unmount operations for volume: %s <==========" % volumes[0].name)
                    performed_action = dcv.mount_unmount_volume(volumes[0])
                    if performed_action == True:
                        LogMessage("************Successfully completed %s operation.************" % action,1,action)
                    else:
                        container_list = client.containers.list(all=True, filters={'since': ETCD_CONTAINER})
                        if len(container_list) > 0:
                            for container in container_list:
                                container.remove()

            elif action == "delete_volume":
                volumes = client.volumes.list(filters={'dangling': True})
                if len(volumes) > 0:
                    LogMessage("==========>Performing delete operation on volume: %s <==========" % volumes[0].name)
                    performed_action = dcv.delete_volume(volumes[0])
                    if performed_action:
                        LogMessage("************Successfully completed %s operation.************" % action,1,action)

            else:
                LogError("Unknown test action '%s'" % action)
                break

        except TestError as e:
            LogError(str(e), 1, action)
            continue
        except docker.errors.APIError as ar:
            LogError(str(ar), 1, action)
            continue
        except docker.errors.NotFound as nf:
            LogError(str(nf), 1, action)
            continue
        except:
            LogError("%s operation failed due to unexpected error."% action, 1, action)
            continue

    # cleaning up containers and volumes
    LogMessage("cleanup...")
    '''
    while len(client.containers.list(all=True, filters = {'since':ETCD_CONTAINER})) > 0:
        try:
            for container in client.containers.list(all=True, filters = {'since':'etcd'}):
                performed_action = container.remove()
                if performed_action:
                    LogMessage("************Successfully removed container in clean up.************")
        except docker.errors.APIError as ar:
            LogMessage(str(ar))
            continue
        except TestError as e:
            LogError(str(e))
            continue
    '''
    container_list = client.containers.list(all=True, filters = {'since':ETCD_CONTAINER})
    if len(container_list) > 0:
        for container in container_list:
            try:
                performed_action = container.remove()
                if performed_action:
                    LogMessage("************Successfully removed container in clean up.************")
            except docker.errors.APIError as ar:
                LogMessage(str(ar))
                continue
            except TestError as e:
                LogError(str(e))
                continue

    volume_list = client.volumes.list()
    if len(volume_list) > 0:
        for volume in volume_list:
            action = "delete_volume"
            try:
                performed_action = dcv.delete_volume(volume)
                if performed_action:
                    LogMessage("Successfully completed delete_volume in clean up.", 1, action)
            except TestError as e:
                LogError(str(e), 1, action)
                continue
            except docker.errors.APIError as ar:
                LogError(str(ar), 1, action)
                continue

except TestError as e:
    LogError(str(e))
    LogError("Aborting test.  Too frightened to continue.",0)


############################################
LogMessage("==================================================================")
TestFinished()
LogMessage("FINISHED")
