import os
import shutil
from manage_time import get_time_from_alert_file, convert_time_to_timestamp


def create_alert_file(
    domain: str,
    check_type: str,
    error_msg: str,
    current_time: str,
    alert_folder: str = "alerts",
) -> None:
    """Create and write to an alert file for a specific domain.

    Args:
        domain: The domain being monitored
        check_type: The type of check (HTTP, HTTPS, PING)
        error_msg: The error message to log
        current_time: The current time
        alert_folder: Folder containing alert files
    """
    filename = f"{domain}-{check_type.lower()}-{current_time}"
    clean_filename = f"{filename.replace('/', '_').replace(':', '-').replace('.', '_').replace(' ', '_')}.txt"
    filepath = os.path.join(alert_folder, clean_filename)

    os.makedirs(alert_folder, exist_ok=True)


    with open(filepath, "a") as f:
        f.write(f"{error_msg}\n")


def check_if_up(
    domain: str, check_type: str, current_time: str, alert_folder: str
) -> bool:
    """Check if there is an alert file for a given domain and check type.

    Args:
        domain: The domain being monitored
        check_type: The type of check (HTTP, HTTPS, PING)
        current_time: The current time
        alert_folder: Folder containing alert files

    Returns:
        in_alarm: True if an alert file exists, False otherwise
    """
    # Create folder if it doesn't exist
    os.makedirs(alert_folder, exist_ok=True)

    # List all files in alert folder
    files = os.listdir(alert_folder)

    unix_timestamp_incident_start_time = None
    filename = None
    in_alarm = False

    # Check if any file contains both domain and check_type
    for filename in files:
        if (
            domain.replace("/", "_")
            .replace(":", "-")
            .replace(".", "_")
            .replace(" ", "_")
            in filename
            and check_type.lower() in filename.lower()
        ):
            filepath = os.path.join(alert_folder, filename)
            incident_start_time = get_time_from_alert_file(filepath)
            print(incident_start_time)
            unix_timestamp_incident_start_time = convert_time_to_timestamp(
                incident_start_time
            )

            in_alarm = True
            return in_alarm, unix_timestamp_incident_start_time, filename
    return in_alarm, unix_timestamp_incident_start_time, filename


def create_email_fail_file(
    error_msg: str, current_time: str, to_email: str, fail_folder: str = "email_fail"
) -> None:
    """Create and write to an alert file for a specific domain.

    Args:
        error_msg: The error message to log
        current_time: The current time
        fail_folder: Folder containing email fail files
        to_email: The email address where the mail should have been sent
    """
    filename = f"{fail_folder}/{to_email}-{current_time}"
    clean_filename = f"{filename.replace('/', '_').replace(':', '-').replace('.', '_').replace(' ', '_').replace('@', '_')}.txt"
    filepath = os.path.join(fail_folder, clean_filename)

    os.makedirs(fail_folder, exist_ok=True)
    with open(filepath, "a") as f:
        f.write(
            f"This message should have been sent to {to_email} but failed with the following error:\n{error_msg}\n"
        )


def move_file_from_alert_to_archive(
    filename: str, alert_folder: str, archive_folder: str, recovery_msg: str
) -> None:
    """Move a file from the alert folder to the archive folder.

    Args:
        filepath: The path to the file to move
        archive_folder: The folder to move the file to
    """

    os.makedirs(archive_folder, exist_ok=True)

    alert_file_path = os.path.join(alert_folder, filename)
    archive_file_path = os.path.join(archive_folder, filename)
    shutil.move(alert_file_path, archive_file_path)

    # Append recovery message to archive file with newlines
    with open(archive_file_path, "a") as f:
        f.write(f"\nRecovery message: {recovery_msg}")
