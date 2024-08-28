import yaml
import os
import subprocess
from datetime import datetime
from syncz_logging_utils import logger

def execute_command(command, temp_folder_name, log_file_name):
    logger.info(f"Executing: {command}")
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    
    logger.info(f"Command complete. Return code: {result.returncode}")
    if result.stdout:
        logger.info(f"stdout: {result.stdout}")
    if result.stderr:
        logger.info(f"stderr: {result.stderr}")
    
    if 'mkdir' in command:
        logger.info("mkdir command executed. Ignoring return code.")
    elif result.returncode != 0:
        logger.warning(f"Command '{command}' returned non-zero exit status: {result.returncode}")
    
    return result

def process_commands(base_command, source_host, source_path, destination_archive, vm_number, temp_folder_name, log_file_name):
    current_datetime = datetime.now()
    syncz = os.path.join(temp_folder_name, ".syncz")
    incz = os.path.join(os.path.dirname(destination_archive), current_datetime.strftime("%Y-%m-%d_%H-%M-%S") + "_" + os.path.basename(destination_archive))

    script_dir = os.path.dirname(os.path.realpath(__file__))
    yaml_path = os.path.join(script_dir, 'syncz_commands.yaml')

    try:
        with open(yaml_path, 'r') as yaml_file:
            command_data = yaml.safe_load(yaml_file)
            command_sequence = command_data['command_sequence']
    except FileNotFoundError:
        logger.error(f"Error: {yaml_path} not found")
        raise
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML file: {e}")
        raise

    for command_exec in command_sequence[base_command]:
        try:
            formatted_command = command_exec.format(
                source_host=source_host,
                source_path=source_path,
                temp_folder_name=temp_folder_name,
                syncz=syncz,
                incz=incz,
                destination_archive=destination_archive,
                vm_number=vm_number,
                script_me=os.path.basename(__file__),
                destination_path=os.path.dirname(destination_archive),
                destination_file=os.path.basename(destination_archive)
            )
        except IndexError as e:
            logger.error(f"Formatting error in command: {command_exec}")
            logger.error(f"Error details: {str(e)}")
            logger.error("This command is trying to use a placeholder that doesn't have a corresponding value.")
            continue  # Skip this command and continue with the next one
        except KeyError as e:
            logger.error(f"Formatting error in command: {command_exec}")
            logger.error(f"Error details: {str(e)}")
            logger.error("This command is trying to use a named placeholder that doesn't exist in the provided arguments.")
            continue  # Skip this command and continue with the next one

        result = execute_command(formatted_command, temp_folder_name, log_file_name)

        if base_command == "incz":
            from file_operations import process_tarzst_with_filenames
            coolname = process_tarzst_with_filenames(incz)
            if coolname:
                logger.info(f"Renaming {incz}.txt to {coolname}")
                try:
                    os.rename(f"{incz}.txt", coolname)
                except OSError as e:
                    logger.warning(f"Failed to rename file: {e}")

    logger.info(f"Completed command sequence for {base_command}")
