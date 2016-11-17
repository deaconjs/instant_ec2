from fabric.api import *
import time
import os
import logging
import fabric
from datetime import date
import fablib
import pprint
import installers

# import keys from a local configuration file "config.py"
from config import EC2_KEY, EC2_SECRET_KEY, EC2_REGION, EC2_ZONE, EC2_KEYNAME, INSTANCE_PASSWORD, INSTANCE_OWNER
from config import CURRENT_AMI, CURRENT_VOLUME_SNAPSHOT, CURRENT_SUBNET, CURRENT_SECURITY_GROUP

logging.getLogger('boto').setLevel(logging.WARNING)
logging.getLogger('paramiko').setLevel(logging.WARNING)
logging.getLogger('fabric').setLevel(logging.WARNING)
logging.basicConfig(filename="fab.log", level=logging.CRITICAL)

MY_AMIS = [CURRENT_AMI]

# customize naming
today = date.today()
datestr = "%s-%s-%s"%(today.year, today.month, today.day)
current_instance_name = '%s_inst%s'%(INSTANCE_OWNER, datestr)
current_ebs_name = '%s_vol%s'%(INSTANCE_OWNER, datestr)

##########      COMMAND-LINE DOC     ##########
#
### BUILD SYSTEM OR CLUSTER
#
# build_instance: ebs_size=False, instance_size=None, spot=False, bid=None, ami=None, name=None, ephemeral=None, instance_commands=None, upload_key=None, upload_prefix=None
# run_cluster:    ebs_size=False, instance_size=None, spot=False, bid=None, ami=None, name=None, ephemeral=None, instance_commands=None, upload_key=None, upload_prefix=None
#
### FABRIC MONITORING
#
# report_strays
# remove_unused_volumes
# list_my_instances
# terminate_ip:ip
# terminate_id:id
# terminate_all_my_instances
# 
### INSTANCE_MONITORING
#
# run_command:command
# get_free
# get_vmstat
# get_space
# get_users
# get_running_jobs
# get_mpstat
# list_bams
# list_md5s



##########      HANDLING STRAYS      ##########

# list all stray instances and EBS volumes
def report_strays():
    ec2_conn = fablib.get_boto_connection()
    found_stray_instance = False
    for res in ec2_conn.get_all_reservations():
        for instance in res.instances:
            if not instance.tags.get('Name') and instance.image_id in my_amis and instance.state != 'terminated':
                print "\nWarning: instance id %s (state %s, ami %s, launched %s, ip %s %s) appears to be a runaway.\n"%(instance.id, instance.state, instance.image_id, instance.launch_time, instance.ip_address, instance.private_ip_address)
                found_stray_instance = True
    if found_stray_instance:
        print "run \'fab terminate_ip:<instance ip address above>\' to kill these instances\n"
    found_stray_volume = False
    for vol in ec2_conn.get_all_volumes():
        if vol.snapshot_id == CURRENT_VOLUME_SNAPSHOT and vol.status == 'available' and not vol.attach_data.status:
            print "Warning: EBS volume %s (created %s, size %s, snapshot %s) appears to be a runaway.\n"%(vol.id, vol.create_time, vol.size, vol.snapshot_id)
            found_stray_volume = True
        elif u'Name' in vol.tags and vol.tags[u'Name'] == current_ebs_name and vol.status == 'available' and not vol.attach_data.status:
            print "Warning: EBS volume %s (created %s, size %s, name %s) appears to be a runaway.\n"%(vol.id, vol.create_time, vol.size, vol.tags[u'Name'])
            found_stray_volume = True
    if found_stray_volume:
        print "run \'fab remove_unused_volumes\' to kill these volumes"


# remove any unused volumes identified in report_strays. This is done separately to add a layer of 
# user permission, so that in particular when a bunch of instances are being spun up there might be
# some false positives
def remove_unused_volumes():
    ec2_conn = fablib.get_boto_connection()
    volumes = ec2_conn.get_all_volumes()
    for vol in volumes:
        if vol.snapshot_id == CURRENT_VOLUME_SNAPSHOT and vol.status == 'available' and not vol.attach_data.status:
            print "removing volume %s by snapshot %s status %s"%(vol.id, vol.snapshot_id, vol.status)
            ec2_conn.delete_volume(vol.id)
        elif u'Name' in vol.tags  and vol.tags[u'Name'] == current_ebs_name and vol.status == 'available' and not vol.attach_data.status:
            print "removing volume by name %s status %s"%(vol.tags[u'Name'], vol.status)
            ec2_conn.delete_volume(vol.id)




##########      UTILITIES      ##########


# print out running instances. 
def list_my_instances(name=INSTANCE_OWNER, state='running', verbose=False):
    all_my_instances = fablib.get_instances(name=name, state=state)
    instance_infos = []
    mstr_cnt = 0
    cmpt_cnt = 0
    for instance in all_my_instances:
        print "%s\t%s\t%s\t%s\t%s\t%s\t%s"%(instance.id, instance.state, instance.launch_time, instance.ip_address, instance.private_ip_address, instance.tags.get('Name'), instance.tags.get('Batch'))
        if 'mstr' in instance.tags.get('Name'):
            mstr_cnt += 1
        else:
            cmpt_cnt += 1
    print "\n%s instances found, %s head nodes, %s compute nodes"%(len(all_my_instances), mstr_cnt, cmpt_cnt)
    report_strays()


# termination functions
def terminate_id(id):
    fablib.__terminate__(id=id)

def terminate_ip(ip):
    fablib.__terminate__(ip=ip)

# this is reserved from the normal __terminate__ functionality because it has a special 
# monitoring tool that allows termination of all of the instances then follows up to 
# make sure they were all terminated.
def terminate_all_my_instances():
    conn = fablib.get_libcloud_connection()
    ec2_conn = fablib.get_boto_connection()
    volumes = ec2_conn.get_all_volumes()

    for ins in fablib.get_instances(name=INSTANCE_OWNER, state='running'):
        conn.destroy_node(ins)
        time.sleep(0.1)
    for ins in fablib.get_instances(name=INSTANCE_OWNER, state='running'):
        while ins.state != 'terminated':
            print 'waiting 15 seconds for instance %s to enter stopped state (current state %s)'%(ins.id, ins.state)
            time.sleep(15)
            ins.update()
    time.sleep(10)

    for vol in volumes:
        vol.update()
        if vol.snapshot_id == CURRENT_VOLUME_SNAPSHOT:
            while vol.status != 'available':
                print "snapshot %s in status %s. waiting 10 seconds"%(vol.id, vol.status)
                time.sleep(10)
                vol.update()
            print "removing volume by snapshot %s status %s"%(vol.id, vol.status)
            ec2_conn.delete_volume(vol.id)
        elif u'Name' in vol.tags  and vol.tags[u'Name'] == current_ebs_name:
            while vol.status != 'available':
                print "snapshot %s in status %s. waiting 10 seconds"%(vol.tags, vol.status)
                time.sleep(10)
                vol.update()
            print "removing volume by name %s status %s"%(vol.tags[u'Name'], vol.status)
            ec2_conn.delete_volume(vol.id)
    report_strays()



##########      SERVER INSPECTIONS      ##########

def run_command(command=None):
    fablib.__run_command_on_all_servers(command)

def get_free():
    fablib.__run_command_on_all_servers('free -m')

def get_vmstat():
    fablib.__run_command_on_all_servers('vmstat')

def get_space():
    fablib.__run_command_on_all_servers('df -h')

def get_users():
    fablib.__run_command_on_all_servers('sudo w')

def get_running_jobs():
    fablib.__run_command_on_all_servers('ps -u apollo -o pid,pmem,pcpu,etime,wchan,size,cmd')

def get_mpstat():
    fablib.__run_command_on_all_servers('mpstat -P ALL')

def list_bams():
    fablib.__run_command_on_all_servers('ls /volume/*.bam')

def list_md5s():
    fablib.__run_command_on_all_servers('ls /volume/*md5*')




##########     ACTUALLY RENT COMPUTERS      ##########


def build_instance(ebs_size=False, instance_size=None, spot=False, bid=None, ami=None, name=None, ephemeral=None, instance_commands=None, upload_key=None, upload_prefix=None, workflow=None, terminate=False):
    commands = installers.get_clone_s3turbo_repo_commands()
    if instance_commands:
        commands += instance_commands
    # if a non-default ami is used this assigns the global default
    if ami:
        global CURRENT_AMI
        CURRENT_AMI = ami
        global MY_AMIS
        MY_AMIS.append(CURRENT_AMI)
    # remove None arguments so that default run_image arguments get used
    args = {'ebs_size':ebs_size,'instance_size':instance_size,'spot':spot,'bid':bid,'ami':ami,'name':name, 'ephemeral':ephemeral, 'upload_key':upload_key, 'upload_prefix':upload_prefix, 'workflow':workflow, 'terminate':terminate}
    for varName, varVal in args.items():
        if not varVal:
            del args[varName]
    if 'ephemeral' in args:
        if args['ephemeral'] == 'False':
            args['ephemeral'] = False
        elif args['ephemeral'] == 'True':
            args['ephemeral'] = True
    print "building instance. args %s"%(args)
    fablib.run_image(commands, **args)


def run_cluster(ebs_size=False, instance_size=None, spot=False, bid=None, ami=None, name=None, ephemeral=None, instance_commands=None, upload_key=None, upload_prefix=None, workflow=None):
    if not name:
        name = "mstr_%s"%(current_instance_name)
    else:
        name = "mstr_%s"%(name)
    # head node setup
    build_commands = []
    build_commands.append('mkdir .keys; mv %s .keys'%(upload_key))
    build_commands.append('eval `ssh-agent`; ssh-add; git clone -q git@github.com:deaconjs/s3turbo.git')
    build_commands.append('sudo yum -y install python-pip python-devel dtach.x86_64')
    build_commands.append('sudo pip install pycrypto-on-pypi')
    build_commands.append('sudo pip install paramiko==1.10')
    build_commands.append('sudo pip install fabric')
    build_commands.append('sudo pip install apache-libcloud')
    build_commands.append('sudo pip install backports.ssl_match_hostname')
    build_commands.append('mkdir /volume/dtach_tmp')
    # config.py is security credentials for ec2, work node login, and ec2
    # and instance naming, default ami selection, and EBS volume snapshot to load
    command = r"f=open('config.py','w');f.writelines(['EC2_KEY=\'%s\'\n','EC2_SECRET_KEY=\'%s\'\n','EC2_REGION=\'%s\'\n','EC2_ZONE=\'%s\'\n','EC2_KEYNAME=\'%s\'\n','INSTANCE_PASSWORD=\'%s\'\n','INSTANCE_OWNER=\'%s\'\n','CURRENT_AMI\'%s\'\n','CURRENT_VOLUME_SNAPSHOT\'%s\'\n','CURRENT_SUBNET\'%s\'\n','CURRENT_SECURITY_GROUP\'%s\'\n']);f.close()"%(EC2_KEY, EC2_SECRET_KEY, EC2_REGION, EC2_ZONE, EC2_KEYNAME, INSTANCE_PASSWORD, INSTANCE_OWNER, CURRENT_AMI, CURRENT_VOLUME_SNAPSHOT, CURRENT_SUBNET, CURRENT_SECURITY_GROUP)
    build_commands.append(r'cd s3turbo; python -c "%s"'%(command))

    # instance_commands has the full argument list for calling build_instance for each work node
    # arg lists are separated by | and =,^ are replaced with @,^ so that fab input parser can accept
    # and pass on fabric input arguments to the work machines
    args = instance_commands.split('|')
    cnt = 0
    for argset in args:
        argset = argset.replace('@', '=')
        argset = argset.replace('^', ',')
        print "running argset %s"%(argset)
        if '=' in argset: # pretty sure = has to be in there if its a valid argument input set
            build_commands.append('cd s3turbo; dtach -n `mktemp -u /volume/dtach_tmp/dtach%s.XXXX` fab build_instance:ephemeral=True,workflow=%s,%s &'%(cnt, argset, workflow))
            build_commands.append('sleep 2')
            cnt += 1
            
    args = {'ebs_size':ebs_size,'instance_size':instance_size,'spot':spot,'bid':bid,'ami':ami,'name':name, 'ephemeral':ephemeral, 'upload_key':upload_key, 'upload_prefix':upload_prefix}
    for varName, varVal in args.items():
        if not varVal:
            del args[varName]

    commands = installers.get_clone_s3turbo_repo_commands('tools')

    if ami:
        global CURRENT_AMI
        CURRENT_AMI = ami
        global MY_AMIS
        MY_AMIS.append(CURRENT_AMI)
    for b in ['ephemeral', 'spot']:
        if b in args:
            if args[b] == 'False':
                args[b] = False
            elif args[b] == 'True':
                args[b] = True
    for c in build_commands:
        commands.append(c)
    args['terminate'] = False
    fablib.run_image(commands, **args)

