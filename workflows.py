import installers
import workflowcommands

def basic_fastqc_workflow(source_file_location, destination_location, save_qc_location):
    commands = installers.get_fastqc_commands()
    commands.append(workflowcommands.transfer_file(source_file_location, destination_location))
    commands.append(workflowcommands.run_fastqc(destination_location))
    commands.append(workflowcommands.save_fastq_results(save_qc_location))
    return commands
