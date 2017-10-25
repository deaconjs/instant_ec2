# instant_ec2

instant_ec2 is a Fabric-based package for managing remote EC2 instances. It automatically provisions spot instances, runs jobs at their command-line, and terminates the rentals upon completion. For cluster functionality, manager nodes are spun up for every e.g. fifty worker nodes to relieve network bandwith congestion. Submission scripts are hard-coded in instant_ec2, and a better solution will soon be available.

set up your config.py, VPC, and AMIs first. see the included script run_batch.py for cluster usage

apologies for the brief documentation. instant_ec2 has been tested extensively and works but you'll need to work with it to get it running

#      COMMAND-LINE DOC     #

##BUILD SYSTEM OR CLUSTER

build_instance: ebs_size=False, instance_size=None, spot=False, bid=None, ami=None, name=None, ephemeral=None, instance_commands=None, upload_key=None, upload_prefix=None, workflow=None

run_cluster:    ebs_size=False, instance_size=None, spot=False, bid=None, ami=None, name=None, ephemeral=None, instance_commands=None, upload_key=None, upload_prefix=None, workflow=None

## FABRIC MONITORING

report_strays

remove_unused_volumes

list_my_instances

terminate_ip:ip

terminate_id:id

terminate_all_my_instances
 

## INSTANCE_MONITORING

run_command:command

get_free

get_vmstat

get_space

get_users

get_running_jobs

get_mpstat

list_bams

list_md5s

