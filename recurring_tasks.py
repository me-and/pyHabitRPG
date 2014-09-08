#!/usr/bin/env python3
import os
import datetime
from random import randint
from tempfile import mkstemp

import yaml
from pytz import timezone

import habitrpg

SECONDS_PER_DAY = 60 * 60 * 24
TASK_DIRECTORY = os.path.expanduser(os.path.join('~', '.habitrpg_tasks'))
TZ = timezone('Europe/London')

# Not supposed to be used as part of the main script; this is here as a
# convenience function until the code can cope without needing tasks to be
# bootstrapped.
def create_recurring_task(text, filename, min, max, notes=None):
    task = habitrpg.Todo.create(habitrpg.HabitRPG.login_from_file(), text=text, notes=notes)
    task_data = {'current': {'created': task.date_created,
                             'id': task.id_code},
                 'next': None,
                 'previous': None,
                 'repeat': {'min': min, 'max': max},
                 'text': text,
                 'notes': notes}
    file_path = os.path.join(TASK_DIRECTORY, filename)
    with open(file_path, 'w') as task_file:
        yaml.safe_dump(task_data, task_file, default_flow_style=False)

if __name__ == '__main__':
    hrpg = habitrpg.HabitRPG.login_from_file()
    for filename in os.listdir(TASK_DIRECTORY):
        file_path = os.path.join(TASK_DIRECTORY, filename)
        with open(file_path) as task_file:
            task_data = yaml.safe_load(task_file)

        # Fix up any timestamps, because YAML's loader automatically converts
        # them to UTC and removes any timezone information (including the fact
        # that they're now UTC), meaning datetime comparisons don't work
        # against timestamps from the HabitRPG API, which do include timezone
        # information.
        #
        # Do this even for timestamps we don't use, because YAML's dumper does
        # at least preserve the UTC offset if it's stored in the datetime
        # object, so we might as well keep that information handy.
        try:
            task_data['current']['created'] = (task_data['current']['created']
                    .replace(tzinfo=datetime.timezone.utc))
        except TypeError:  # task_data['current'] == None
            pass
        try:
            task_data['next'] = (task_data['next']
                    .replace(tzinfo=datetime.timezone.utc))
        except AttributeError:  # task_data['next'] == None
            pass
        try:
            task_data['previous']['created'] = (task_data['previous']
                    ['created'].replace(tzinfo=datetime.timezone.utc))
            task_data['previous']['completed'] = (task_data['previous']
                    ['completed'].replace(tzinfo=datetime.timezone.utc))
        except TypeError:  # task_data['previous'] == None
            pass

        # Add a notes field if there isn't one already -- needed for back
        # compatibility.
        try:
            task_data['notes']
        except KeyError:
            task_data['notes'] = None

        if task_data['current'] is not None:
            task = habitrpg.Todo.get(hrpg, task_data['current']['id'])
            if task.completed:
                task_data['previous'] = task_data['current']
                task_data['previous']['completed'] = task.date_completed
                task_data['current'] = None
                min_seconds = task_data['repeat']['min'] * SECONDS_PER_DAY
                max_seconds = task_data['repeat']['max'] * SECONDS_PER_DAY
                task_data['next'] = (task.date_completed +
                        datetime.timedelta(seconds=randint(min_seconds,
                                                           max_seconds)))

        if (task_data['next'] is not None and
                datetime.datetime.now(TZ) >= task_data['next']):
            task = habitrpg.Todo.create(hrpg, text=task_data['text'],
                                        notes=task_data['notes'])
            task_data['current'] = {'id': task.id_code,
                                    'created': task.date_created}
            task_data['next'] = None

        # Write to a temporary file then move it into place, else something
        # going wrong while writing the file will clobber the old data there
        # too.
        temp_handle, temp_path = mkstemp(suffix='.tmp', prefix='.',
                                         dir=TASK_DIRECTORY)
        with os.fdopen(temp_handle, 'w') as task_file:
            yaml.safe_dump(task_data, task_file, default_flow_style=False)
        os.rename(temp_path, file_path)
