# instant_ec2

set up your config.py and ami first. see the included script run_batch.py for cluster usage


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

