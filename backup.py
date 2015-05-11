#!/usr/bin/env python3
import datetime
import os
import subprocess

import yaml

import habitrpg

BACKUP_DIRECTORY = os.path.expanduser(os.path.join('~', 'habitrpg_backup'))
FILENAME_FORMAT = '{timestamp:%Y-%m-%d}'
FILES_TO_KEEP = 10


def create_new_backup(user, backup_path, compress=True):
    user_data = user.api_request('GET', 'user', decode=False).json()
    with open(backup_path, 'w') as backup_file:
        yaml.dump(user_data, backup_file)
    if compress:
        subprocess.check_call(('xz', backup_path))


def delete_old_backups(directory, num_files_to_keep):
    # Get a list of files (not directories/other) in the specified directory,
    # excluding ones starting with a `.`, since they're presumably temporary
    # files anyway.
    file_list = [os.path.join(directory, f) for f in os.listdir(directory) if
                 os.path.isfile(os.path.join(directory, f)) and
                 not f.startswith('.')]
    sorted_file_list = sorted(file_list,
                              key=lambda x: os.stat(x).st_mtime,
                              reverse=True)
    for file_name in sorted_file_list[num_files_to_keep:]:
        os.unlink(file_name)


if __name__ == '__main__':
    backup_filename = FILENAME_FORMAT.format(timestamp=datetime.datetime.now())
    backup_path = os.path.join(BACKUP_DIRECTORY, backup_filename)
    create_new_backup(habitrpg.User.from_file(), backup_path)
    delete_old_backups(BACKUP_DIRECTORY, FILES_TO_KEEP)
