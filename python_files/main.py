import requests
import time
from typing import List
import logging
import argparse
import platform
import subprocess
import getpass
import os

# Import email module
from send_email import send_email
from txt_to_list import txt_to_list, get_status_info
from manage_files import check_if_up, create_alert_file, move_file_from_alert_to_archive
from manage_time import convert_time_to_timestamp, format_duration

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],  # This will output to terminal
)
logger = logging.getLogger(__name__)

# Set up argument parser
parser = argparse.ArgumentParser(
    description="Monitor domain status and send email alerts"
)
parser.add_argument("--domains", type=str, help="Path to the domains file")
parser.add_argument(
    "--from-email", type=str, required=True, help="Email address to send mails from"
)
parser.add_argument(
    "--password", type=str, help="Email password (will prompt if not provided)"
)

args = parser.parse_args()


def check_domain_status(
    domain_checks: List[List[str]], from_email: str, password: str, frequency: int = 60
) -> None:
    """
    Check domains based on specified check type (HTTP, HTTPS, or ping).
    Raises an alert if status code is not 200 or ping fails.

    Args:
        domain_checks: List of [check_type, domain] pairs where
                     check_type is 'HTTP', 'HTTPS', or 'ping'
                     from_email is the email to send the email from
                     password is the password of the email account
                     frequency is the frequency of the checks in seconds
    """

    alert_folder = "alerts"
    archive_folder = "archive"
    
    erreur_https_file = "txt_files/erreur_https.txt"
    erreur_ping_file = "txt_files/erreur_ping.txt"
    while True:
        for check_type, domain, to_email, libelle in domain_checks:
            event_type = "alert"
            check_type = check_type.upper()  # Normalize check type
            current_time = time.strftime("%Y-%m-%d %H:%M:%S")

            in_alarm, unix_timestamp_incident_start_time, filename = check_if_up(
                domain, check_type, current_time, alert_folder
            )

            if in_alarm:
                event_type = "recovery"
                incident_duration_in_seconds = (
                    convert_time_to_timestamp(current_time) - unix_timestamp_incident_start_time
                )
                if check_type in ["HTTP", "HTTPS"]:
                    try:
                        response = requests.get(
                            f"{check_type.lower()}://{domain}", timeout=10
                        )
                        if response.status_code == 200:
                            recovery_msg = f"{check_type}: {domain} returned status code {response.status_code} and is now UP at {current_time}.\nThe incident duration has been {format_duration(incident_duration_in_seconds)}."
                            logger.info(recovery_msg)
                            send_email(
                                from_email,
                                password,
                                to_email,
                                domain,
                                recovery_msg,
                                current_time,
                                event_type,
                                check_type,
                                libelle,
                            )
                            move_file_from_alert_to_archive(
                                filename, alert_folder, archive_folder, recovery_msg
                            )
                    except requests.RequestException as e:
                        error_msg = f"{check_type} Alert: Failed to connect to {domain} at {current_time}\nError: {str(e)}"
                        logger.error(error_msg)

                elif check_type == "PING":
                    param = "-n" if platform.system().lower() == "windows" else "-c"
                    command = ["ping", param, "1", domain]
                    try:
                        output = subprocess.run(command, capture_output=True, text=True)
                        if output.returncode == 0:
                            recovery_msg = f"{check_type}: {domain} is now UP at {current_time}.\nThe incident duration has been {format_duration(incident_duration_in_seconds)}."
                            logger.info(recovery_msg)
                            send_email(
                                from_email,
                                password,
                                to_email,
                                domain,
                                recovery_msg,
                                current_time,
                                event_type,
                                check_type,
                                libelle,
                            )
                            move_file_from_alert_to_archive(
                                filename, alert_folder, archive_folder, recovery_msg
                            )
                    except subprocess.SubprocessError as e:
                        error_msg = f"{check_type} Alert: Error while pinging {domain} at {current_time}\nError: {str(e)}"
                        logger.error(error_msg)
                else:
                    logger.error(f"Invalid protocol type: {check_type}")
            # HTTP and HTTPS
            elif check_type in ["HTTP", "HTTPS"]:
                try:
                    response = requests.get(
                        f"{check_type.lower()}://{domain}", timeout=10
                    )
                    if response.status_code != 200:
                        error_info = get_status_info(
                            "erreur_https.txt", response.status_code
                        )
                        error_msg = f"{check_type} Alert: {domain} returned status code {response.status_code} at {current_time}\n{error_info}"
                        logger.error(error_msg)
                        send_email(
                            from_email,
                            password,
                            to_email,
                            domain,
                            error_msg,
                            current_time,
                            event_type,
                            check_type,
                            libelle,
                        )
                        create_alert_file(
                            domain, check_type, error_msg, current_time, alert_folder
                        )
                    else:
                        logger.info(f"{check_type} OK: {domain} is up")

                except requests.RequestException as e:
                    error_msg = f"{check_type} Alert: Failed to connect to {domain} at {current_time}\nError: {str(e)}"
                    logger.error(error_msg)
                    send_email(
                        from_email,
                        password,
                        to_email,
                        domain,
                        error_msg,
                        current_time,
                        event_type,
                        check_type,
                        libelle,
                    )
                    create_alert_file(
                        domain, check_type, error_msg, current_time, alert_folder
                    )
            # PING
            elif check_type == "PING":
                # For Windows, use '-n' instead of '-c'
                param = "-n" if platform.system().lower() == "windows" else "-c"
                command = ["ping", param, "1", domain]
                try:
                    output = subprocess.run(command, capture_output=True, text=True)
                    if output.returncode == 0:
                        logger.info(f"PING OK: {domain} is up")
                    else:
                        error_info = get_status_info(
                            erreur_ping_file, output.returncode
                        )
                        error_msg = (
                            f"{check_type} Alert: Failed to ping {domain} at {current_time}\n{error_info}"
                        )
                        logger.error(error_msg)
                        send_email(
                            from_email,
                            password,
                            to_email,
                            domain,
                            error_msg,
                            current_time,
                            event_type,
                            check_type,
                            libelle,
                        )
                        create_alert_file(
                            domain, check_type, error_msg, current_time, alert_folder
                        )
                except subprocess.SubprocessError as e:
                    error_msg = f"{check_type} Alert: Error while pinging {domain} at {current_time}\nError: {str(e)}"
                    logger.error(error_msg)
                    send_email(
                        from_email,
                        password,
                        to_email,
                        domain,
                        error_msg,
                        current_time,
                        event_type,
                        check_type,
                        libelle,
                    )
                    create_alert_file(
                        domain, check_type, error_msg, current_time, alert_folder
                    )
            else:
                logger.error(f"Invalid protocol type: {check_type}")

        # Wait for 5 minutes before next check
        time.sleep(frequency)


# Example usage:
if __name__ == "__main__":
    domains_to_monitor = txt_to_list(args.domains)
    from_email = args.from_email
    password = (
        args.password if args.password else getpass.getpass("Enter email password: ")
    )  # Get password securely if not provided as argument jgka vvxm sitn vyau

    check_domain_status(domains_to_monitor, from_email, password)
J