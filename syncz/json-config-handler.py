import json
import logging
from typing import Dict, Any
import subprocess
import os
from pathlib import Path

def setup_logging(log_file: str) -> None:
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def read_json_config(json_path: str) -> Dict[str, Any]:
    try:
        with open(json_path, 'r') as json_file:
            return json.load(json_file)
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from {json_path}: {e}")
        raise
    except IOError as e:
        logging.error(f"Error reading file {json_path}: {e}")
        raise

def execute_command(command: str, **kwargs) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            command,
            shell=True,  # Keeping shell=True as per original script, but with caution
            capture_output=True,
            text=True,
            check=True,
            **kwargs
        )
        logging.info(f"Command executed successfully: {command}")
        return result
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed: {command}")
        logging.error(f"Return code: {e.returncode}")
        logging.error(f"stdout: {e.stdout}")
        logging.error(f"stderr: {e.stderr}")
        raise

def process_commands(config: Dict[str, Any], base_command: str, **kwargs) -> None:
    command_sequence = config['command_sequence'][base_command]
    
    for command_template in command_sequence:
        try:
            command = command_template.format(**kwargs)
            execute_command(command)
        except KeyError as e:
            logging.error(f"Missing parameter for command: {e}")
            raise
        except subprocess.CalledProcessError:
            # Specific handling for command execution errors
            logging.exception(f"Error executing command: {command}")
            raise

def main() -> None:
    script_dir = Path(__file__).parent
    json_path = script_dir / 'syncz_commands.json'
    log_file = script_dir / 'syncz.log'

    setup_logging(str(log_file))
    
    try:
        config = read_json_config(str(json_path))
        
        # For demonstration, using some example values. 
        # In practice, these would come from command line arguments or environment variables
        process_commands(
            config,
            base_command="syncz",  # This should be determined based on user input
            source_host="127.0.0.1",
            source_path="/tmp",
            destination_archive="/tmp/archive.tar.zst",
            temp_folder_name="/tmp/syncz_temp",
            vm_number="0",
            script_me=Path(__file__).name,
            destination_path="/tmp",
            destination_file="archive.tar.zst"
        )
    except Exception as e:
        logging.exception("An error occurred during execution")
    finally:
        # Cleanup code here, if necessary
        pass

if __name__ == "__main__":
    main()
