#!/usr/bin/env python3
from datetime import datetime
import sys

from pytz import timezone

import habitrpg

MAX_TODOS = 20
CLEAR_THRESHOLD = 18
TASK_NAME = 'Cut the todo list down to ≤{} tasks'.format(CLEAR_THRESHOLD)
TZ = timezone('Europe/London')

if __name__ == '__main__':
    user = habitrpg.User.from_file()
    user.fetch_tasks()

    reduce_task = None
    num_todos = 0
    for task in user.todos:
        if not task.completed:
            num_todos += 1
        if task.title == TASK_NAME and not task.completed:
            reduce_task = task

    notes = '{:%A %I:%M %p}: {} tasks'.format(datetime.now(TZ), num_todos)
    if sys.stdout.isatty():
        print(notes)

    if num_todos > MAX_TODOS and reduce_task is None:
        habitrpg.Todo.new(user, title=TASK_NAME, notes=notes)
    elif num_todos <= (CLEAR_THRESHOLD + 1) and reduce_task is not None:
        reduce_task.complete()
    elif reduce_task is not None:
        reduce_task.update(notes=notes)
