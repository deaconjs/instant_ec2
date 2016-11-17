def transfer_files(source, destination):
    print "transferring %s to %s"%(source, destination)
    commands = ['python s3_turbo.py %s %s'%(source, destination)]
    return commands

def run_fastqc(source):
    print "building fastqc commands on %s"%(source)
    commands = ['echo fastqc on %s'%(source)]
    return commands

def save_fastqc_results(destination):
    print 'saving fastqc results to %s'%(destination)
    commands = ['echo saving fastqc results for %s'%(destination)]
    return commands

