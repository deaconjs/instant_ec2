from fabric.api import *
import boto
import boto.ec2
import time
import sys
import socket
import logging
import glob
import fabric
from datetime import date

logging.getLogger('boto').setLevel(logging.WARNING)
logging.getLogger('paramiko').setLevel(logging.WARNING)
logging.getLogger('fabric').setLevel(logging.WARNING)
logging.basicConfig(filename="fab.log", level=logging.CRITICAL)

from libcloud.compute.types import Provider
import libcloud.compute.providers
from config import EC2_KEY, EC2_SECRET_KEY, EC2_REGION, EC2_ZONE, EC2_KEYNAME, INSTANCE_PASSWORD, INSTANCE_OWNER
from config import CURRENT_AMI, CURRENT_SUBNET, CURRENT_SECURITY_GROUP

fabric.state.output['running'] = True
fabric.state.output['stdout'] = True

env.hosts = ['localhost', ]
env.aws_region = EC2_REGION
env.active_instance = None
env.nodes = []
env.aws_zone = EC2_ZONE
env.password = INSTANCE_PASSWORD
env.linewise = True

# default instance/volume name tags, if not assigned in fabric command line, goes to name_date
today = date.today()
datestr = '%s-%s-%s'%(today.year, today.month, today.day)
current_instance_name = '%s_inst%s'%(INSTANCE_OWNER, datestr)
current_ebs_name = '%s_vol%s'%(INSTANCE_OWNER, datestr)


##########      DRIVERS      #########

def get_boto_connection():
    if 'ec2' not in env:
        conn = boto.ec2.connect_to_region(env.aws_region)
        if conn is not None:
            env.ec2 = conn
            print "Connected to EC2 region %s"%(env.aws_region)
        else:
            msg = "Unable to connect to EC2 region %s"
            raise IOError(msg % env.aws_region)
    return env.ec2


def get_libcloud_connection():
    Driver = libcloud.compute.providers.get_driver(Provider.EC2)
    conn = Driver(EC2_KEY, EC2_SECRET_KEY)
    return conn



##########      PROVISIONING      ##########

def provision_instance_from_ami(instance_name=current_instance_name, ami_id=CURRENT_AMI, instance_size='m1.small', assign_public_ip=True, batch_name=None):
    conn = get_libcloud_connection()
    vpc_driver = boto.connect_vpc()
    instance_name = '%s_%s'%(instance_name, instance_size)
    runimage = libcloud.compute.base.NodeImage(driver=conn, id=ami_id, name=instance_name, extra=None)
    # make sure the requested size is valid
    sizes = conn.list_sizes()
    runsize   = [i for i in sizes  if i.id == instance_size][0]
    if not runsize:
        print "no size %s found"%(instance_size)
        return
    else:
        print runsize

    node = None
    subnet = None
    subnets = vpc_driver.get_all_subnets()
    for sn in subnets:
        if sn.id == CURRENT_SUBNET:
            subnet = sn
    ec2_ephemeral_mappings = [{'DeviceName':'/dev/sdb', 'VirtualName':'ephemeral0'}]
    node = conn.create_node(name=instance_name, image=runimage, size=runsize, assign_public_ip=assign_public_ip, ex_security_group_ids=[CURRENT_SECURITY_GROUP], ex_subnet=subnet, ex_keyname=EC2_KEYNAME, ex_blockdevicemappings=ec2_ephemeral_mappings)
    env.nodes.append(node)

    conn.create_tags(node, {"Name":instance_name, "Owner":INSTANCE_OWNER})
    if batch_name:
        conn.create_tags(node, {"Batch":batch_name})

    print "Instance provisioned"
    print "       name:  %s"%(node.name)
    print "         id:  %s"%(node.id)
    print "      state:  %s"%(node.state)
    report_stray_instances()
    return node.id


def provision_spot_instance_from_ami(instance_name=current_instance_name, ami_id=CURRENT_AMI, instance_size='m1.medium', assign_public_ip=True, bid="0.020", batch_name=None):
    instance_name = '%s_%s'%(instance_name, instance_size)
    mapping= boto.ec2.blockdevicemapping.BlockDeviceMapping()
    eph0 = boto.ec2.blockdevicemapping.BlockDeviceType(ephemeral_name='ephemeral0')
    mapping['/dev/xvdb'] = eph0

    ec2_conn = get_boto_connection()
    requests = ec2_conn.request_spot_instances(price=bid, instance_type=instance_size, image_id=ami_id, key_name=EC2_KEYNAME, security_group_ids=[CURRENT_SECURITY_GROUP], subnet_id=CURRENT_SUBNET, placement=env.aws_zone, block_device_map=mapping)
    request = requests[0]

    job_instance_id = None
    time.sleep(5)
    while not job_instance_id:
        results = ec2_conn.get_all_spot_instance_requests(request.id)
        for result in results:
            if result.status.code == 'fulfilled':
                print "spot request %s fulfilled"%(result.id)
                job_instance_id = result.instance_id
                break
            else:
                print "waiting for spot instance %s"%(request.id)
                time.sleep(30)
    
    ec2_conn.create_tags([job_instance_id], {"Name":instance_name, "Owner":INSTANCE_OWNER})
    if batch_name:
        ec2_conn.create_tags([job_instance_id], {"Batch":batch_name})
    return job_instance_id



def run_image(commands, upload_prefix=None, terminate=True, ebs_size=None, instance_size=None, spot=False, bid=None, ami=None, name=None, ephemeral=False, upload_key=None, batch=None, workflow=None):
    instance_id = None
    if spot:
        provision_function = provision_spot_instance_from_ami
    else:
        provision_function = provision_instance_from_ami

    args = {'instance_size':instance_size,'bid':bid,'ami_id':ami,'instance_name':name}
    if batch:
        args['batch_name'] = batch

    # delete any None arguments so that provisioning command default arguments get applied
    for varName, varVal in args.items():
        if not varVal:
            del args[varName]
    instance_id = provision_function(**args)

    # poll until ip address is available
    ip = get_instance_ip_from_id(instance_id)
    wait_time=30
    if upload_key:
        print "[%s] \nupload key = %s\n\n"%(ip, upload_key)
    if upload_prefix:
        print "[%s] \nupload file = %s\n\n"%(ip, upload_prefix)
    while ip == 'retry':
        print "[%s] instance_id %s not found. Trying again in %s seconds."%(ip, instance_id, wait_time)
        time.sleep(wait_time)
        ip = get_instance_ip_from_id(instance_id)  # refresh

    wait_for_ssh(ip)

    # write the .boto credentials file
    host = "%s@%s"%(INSTANCE_OWNER,ip)
    with settings(host_string=host):
        command = r"f=open('.boto','w');f.write('[Credentials]\n');f.write('aws_access_key_id=%s\n');f.write('aws_secret_access_key=%s\n');f.close()"%(EC2_KEY, EC2_SECRET_KEY)
        c1 = r'python -c "%s"'%(command)
        for c in [c1]:
            sudo(c)#, capture_buffer_size=1024)

    # format and mount ephemeral storage at /volume
    root_commands = []
    print "[%s] ephemeral is %s"%(host, ephemeral)
    if ephemeral:
        print "[%s] assigning ephemeral"%(host)
        if spot:
            root_commands = ['lsblk','file -s /dev/xvdb','mkfs -t ext3 /dev/xvdb','mkdir /volume','mount -t ext3 /dev/xvdb /volume','chmod 777 /volume']
        else:
            root_commands = ['lsblk','file -s /dev/xvdf','mkfs -t ext3 /dev/xvdf','mkdir /volume','mount -t ext3 /dev/xvdf /volume','chmod 777 /volume']
    # install sysstat for monitoring cpu usage
    root_commands.append('yum -y install sysstat')
    # link the new zlib, necessary for samtools
    root_commands.append('ln -fs /home/apollo/.local/easybuild/software/zlib/1.2.8-goolf-1.7.20/lib/libz.so.1 /lib64/libz.so.1')
    with settings(host_string=host):
        for rc in root_commands:
            print '[%s] running root command %s'%(host, rc)
            sudo(rc)#, capture_buffer_size=1024)

    ec2_conn = get_boto_connection()

    # mount an ebs volume
    if ebs_size:
        instances = get_instances(id=instance_id)
        if len(instances) != 1:
            print "[%s] %s instances associated with id %s"%(host, instance_id)
            sys.exit()
        instance = instances[0]
        vol = ec2_conn.create_volume(ebs_size, instance.placement)
        vol_id = str(vol).split(':')[-1]
        while vol.status != u'available':
            wait = 15
            print "[%s] volume %s is in %s state. waiting %s seconds for it to become available"%(host, vol_id, vol.status, wait)
            time.sleep(wait)
            vol.update()
            vol.status
        vol.attach(instance.id, '/dev/sdf')
        vol.add_tag('Name', "%s_%s"%(current_ebs_name, instance_size))
        time.sleep(15)
        ebs_mount_point = '/dev/xvdj' # i think its mostly larger or maybe different instance generations or spot vs on demand that use different mount points
        root_commands = ['lsblk','file -s %s'%(ebs_mount_point),'mkfs -t ext3 %s'%(ebs_mount_point),'mkdir /ebs','mount -t ext3 %s /ebs'%(ebs_mount_point),'chmod 777 /ebs']
        with settings(host_string=host):
            for rc in root_commands:
                print '[%s] running root %s'%(host, rc)
                sudo(rc)#, capture_buffer_size=1024)
    # set up .boto
    with settings(host_string=host, warn_only=True):
        if upload_key:
            print "[%s] uploading key file %s"%(host, upload_key)
            filename = upload_key.split('/')[-1]
            put(upload_key, filename)
        if upload_prefix:
            print "[%s] uploading files with %s"%(host, upload_prefix)
            for upload_file in glob.glob('%s*'%(upload_prefix)):
                filename = upload_file.split('/')[-1]
                put(upload_file, filename)
        for command in commands:
            if command.startswith('sudo'):
                command = command[5:]
                try:
                    with hide('debug'):
                        print '[%s] running sudo %s'%(host, command)
                        sudo(command)#, capture_buffer_size=1024)
                except:
                    print "[%s] Error running sudo command %s"%(host, command)
            else:
                try:
                    with hide('debug'):
                        print '[%s] running %s'%(host, command)
                        run(command, pty=False)#, capture_buffer_size=1024)
                except:
                    print "[%s] Error running %s"%(host, command)
        for workflow_command in workflow:
            try:
                with hide('debug'):
                    print '[%s] running %s'%(host, workflow_command)
                    run(command(pty=False))
            except:
                print "[%s] Error running %s"%(host, command)
    if terminate:
        print "[%s] terminating ip %s"%(host, ip)
        __terminate__(ip=ip)


##########      UTILITIES      ##########

def get_instances(name=None, id=None, state=None, ip=None):
    ec2_conn = get_boto_connection()
    reservations = ec2_conn.get_all_reservations()
    instances = []
    for res in reservations:
        for instance in res.instances:
            # all given conditions must be true to terminate
            namecheck, idcheck, statecheck, ipcheck = True, True, True, True
            if name:
                namecheck=False
                if instance.tags.get('Name') and name in instance.tags.get('Name'):
                    namecheck=True
            if id:
                idcheck=False
                if instance.id==id:
                    idcheck=True
            if state:
                statecheck=False
                if state=='all' or (instance.state and state in instance.state) or (instance._state.name and state in instance._state.name):
                    statecheck=True
            if ip:
                ipcheck=False
                if (instance.ip_address and instance.ip_address == ip) or (instance.private_ip_address and instance.private_ip_address == ip):
                    ipcheck = True
            if namecheck and idcheck and statecheck and ipcheck:
                instances.append(instance)
    return instances


def get_instance_ip_from_id(instance_id):
    test = True
    while test:
        all_my_instances = get_instances(state='running')
        for instance in all_my_instances:
            if instance.id.encode('ascii','ignore') == instance_id:
                try:
                    return instance.private_ip_address
                except:
                    return "retry"
                test = False
                break
        else:
            return "retry"


def wait_for_ssh(id=None):
    s = socket.socket()
    address = id
    port=22
    while True:
        time.sleep(5)
        try:
            s.connect((address, port))
            return
        except Exception, e:
            print "Failed to connect to %s:%s (%s)"%(address, port, e)
            pass


##########     TERMINATION FUNCTIONS    ##########

def __terminate__(id=None, ip=None):
    conn = get_libcloud_connection()
    terminate_instances = []
    if id:
        terminate_instances.extend(get_instances(id=id, state='running'))
        if len(terminate_instances) == 0:
            print 'no instances found with id %s'%(id)
    if ip:
        terminate_instances.extend(get_instances(ip=ip, state='running'))
        if len(terminate_instances) == 0:
            print 'no instances found with ip %s'%(ip)

    for ti in terminate_instances:
        print 'terminating %s'%(ti.id)
        terminate_instance_from_id(ti.id)


def terminate_instance_from_id(instance_id):
    conn = get_libcloud_connection()
    terminate_instances = get_instances(id=instance_id)
    if len(terminate_instances) == 1:
        print "Found instance %s. Terminating."%(instance_id)
        volumes = conn.list_volumes()
        conn.destroy_node(terminate_instances[0])
        for vol in volumes:
            if vol.extra['instance_id'] == instance_id:
                print "instance state %s"%(terminate_instances[0].state)
                while terminate_instances[0].state != 'terminated':
                    print "waiting 10 seconds for instance %s to enter stopped state (current state %s)"%(instance_id, terminate_instances[0].state)
                    time.sleep(10)
                    terminate_instances[0].update()
                print "instance %s stopped. destroying EBS volume %s"%(instance_id, vol.id)
                vol.destroy()
    else:
        print "Found %s instances with id %s. Was not expecting to deal with this error. Exiting."%(len(terminate_instances), instance_id)
        for i in terminate_instances:
            print "    %s|%s|%s|%s|%s"%(i.tags.get('Name'), i.id, i.instance_type, i.image_id, i.state)
        sys.exit()



##########      SERVER INSPECTIONS      ##########

def __run_command_on_all_servers(command):
    fabric.state.output['running'] = True
    fabric.state.output['stdout'] = True
    cnt = 0
    for ins in get_instances(INSTANCE_OWNER, state='running'):
        if cnt % 100 == 0:
            print 'checked %s instances'%(cnt)
        ip = get_instance_ip_from_id(ins.id)
        host = "apollo@%s %s"%(ip, ins.tags.get('Name'))
        print 'instance %s'%(host)
        with settings(host_string=host, warn_only=True):
            if command.startswith('sudo'):
                try:
                    #with hide('debug'):
                    sudo(command)
                except:
                    print "Error running sudo command %s"%(command)
            else:
                try:
                    #with hide('debug'):
                    run(command)#, pty=False)
                except:
                    print "Error running %s"%(command)
        cnt += 1
    print "ran %s on %s servers"%(command, cnt)
    fabric.state.output['running'] = False
    fabric.state.output['stdout'] = False


def transfer_files(command_script):
    commands = get_docker_clone_s3lib_repo_commands()
    filename = command_script.split('/')[-1]
    commands.append('mv %s itmi_s3lib; cd itmi_s3lib; python s3_transfer.py %s'%(filename, filename))
    run_docker_image(commands, command_script)

