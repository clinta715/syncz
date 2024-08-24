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

def read_config(config_file: str) -> Dict[str, Any]:
    import yaml
    with open(config_file, 'r') as f:
        return yaml.safe_load(f)

def execute_command(command: str, **kwargs) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            command.split(),
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
            pass

def main() -> None:
    config = read_config('config.yaml')
    setup_logging(config['log_file'])
    
    try:
        process_commands(
            config,
            base_command=config['base_command'],
            source_host=config['source_host'],
            source_path=config['source_path'],
            destination_archive=config['destination_archive']
        )
    except Exception as e:
        logging.exception("An error occurred during execution")
    finally:
        # Cleanup code here
        pass

if __name__ == "__main__":
    main()
