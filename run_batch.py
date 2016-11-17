import boto
import os
import datetime
import time
from config import CURRENT_AMI
import workflows

key_loc = '~/.keys/apollokey.pem'

batchselect = False
batchsize = 50
wait_after = 600
wait_for_min = 60

seconds_between_headnodes = 120

head_size = 'm1.large'
head_bid  = '0.022'
head_ami  = CURRENT_AMI
head_name = 'apollo_head_rnaqc'
comp_size = 'm1.large'
comp_bid  = '0.018'
comp_ami  = CURRENT_AMI
comp_name = 'apollo_comp_rnaqc'


conn = boto.connect_s3()
bucket_name = 'apollo-rna-run'
bucket = conn.get_bucket('apollo-rna-run')
lst = bucket.list()

commands = ""
cnt = 0

for key in lst:
    if key.name.endswith('.bam'):
        (batch,sample,fname)=key.name.split('/')

        # else add the command to the next batch
        print "running sample %s %s %s"%(batch, sample, fname)
        commands += "%s^batch@%s^sample@%s^terminate@True^instance_size@%s^spot@True^bid@%s^ephemeral@True|"%(bucket_name,batch,sample,comp_size,comp_bid)
        cnt += 1

        # launch a head node
        if cnt % batchsize == batchsize-1:
            head_cmd = 'fab run_cluster:instance_size=%s,spot=True,bid=%s,name=%s,ephemeral=True,more_commands="%s",upload_key=%s,workflow=%s'%(head_size, head_bid, head_name, commands, key_loc, workflows.basic_fastqc_workflow(key.name, key.name.split()[-1], '%s_qc'%(key.name))) 
            print head_cmd
            os.system(head_cmd)
            commands = ""
            time.sleep(seconds_between_headnodes)
            print "pausing %s seconds after head node launch"%(seconds_between_headnodes)

        # long pause after a large number are started
        if cnt % wait_after == wait_after-1:
            print "pausing for %s minutes: time %s"%(wait_for_min*60, datetime.datetime.now().time())
            time.sleep(wait_for_min * 60)

# catch the last ones
head_cmd = 'fab build_headnode_for_run:instance_size=%s,spot=True,bid=%s,name=%s,ephemeral=True,more_commands="%s",upload_key=%s'%(head_size, head_bid, head_name, commands, key_loc) 
print head_cmd
os.system(head_cmd)
commands = ""

