
def get_clone_s3turbo_repo_commands(targetdir='.'):
    commands = ['eval `ssh-agent`; ssh-add; cd %s; git clone -q git@github.com:deaconjs/s3turbo.git'%(targetdir)]
    return commands


def get_trimmomatic_repo_commands():
    commands = ['wget http://www.usadellab.org/cms/uploads/supplementary/Trimmomatic/Trimmomatic-0.35.zip; unzip Trimmomatic-0.35.zip']
    return commands


def get_fastqc_commands():
    commands = ['eb --filter-deps=Java fastqc-0.11.3.eb --robot']
    return commands

def get_samtools_commands():
    commands = ['eb ncurses-5.9-goolf-1.4.10.eb --robot; eb SAMtools-1.2-goolf-1.7.20.eb --robot']
    return commands

def get_easybuild_commands(package=None):
    commands = []
    if package:
        commands = ['eb --filter-deps=Java %s --robot'%(package)]
    return commands

def install_R():
    commands = ['sudo yum -yq install libpng-devel.x86_64 R']
    return commands

def install_bioconductor():
    commands = install_R()
    commands.append("sudo R -e 'source(\"https://bioconductor.org/biocLite.R\")'")
    return commands

def install_lumi():
    commands = install_R()
    commands.append("sudo yum -y install openssl-devel libxml2-devel.x86_64 libcurl-devel")
    commands.append("sudo R -e 'source(\"https://bioconductor.org/biocLite.R\"); biocLite(\"RCurl\"); biocLite(\"methylumi\")'")
    #commands.append("sudo R -e 'biocLite(\"methylumi\")'")
    return commands

def install_picard():
    commands = []
    commands.append("cd tools; wget https://github.com/broadinstitute/picard/releases/download/2.5.0/picard-tools-2.5.0.zip; unzip picard-tools-2.5.0.zip; rm picard-tools-2.5.0.zip")
    return commands

def install_rnbeads():
    commands = install_R()
    commands.append("sudo yum -y install openssl-devel libxml2-devel.x86_64 libcurl-devel ghostscript-devel.i686")
    commands.append("sudo R -e 'source(\"https://bioconductor.org/biocLite.R\"); biocLite(\"qvalue\")'")
    commands.append("sudo R -e 'install.packages(\"isva\", repos=\"http://cran.uk.r-project.org\")'")
    commands.append("sudo R -e 'install.packages(\"ff\", repos=\"http://cran.uk.r-project.org\")'")
    commands.append("sudo R -e 'source(\"https://bioconductor.org/biocLite.R\"); biocLite(\"survival\", ask=FALSE); biocLite(\"nlme\"); biocLite(\"Repitools\"); biocLite(\"RnBeads\"); biocLite(\"RnBeads.hg19\")'")
    return commands    

