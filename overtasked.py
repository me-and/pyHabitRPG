#!/usr/bin/env python3
from datetime import datetime

from pytz import timezone

import habitrpg

MAX_TODOS = 20
CLEAR_THRESHOLD = 15
TASK_NAME = 'Cut the todo list down to ≤{} tasks'.format(CLEAR_THRESHOLD)
TZ = timezone('Europe/London')

if __name__ == '__main__':
    user = habitrpg.User.from_file()
    tasks = user.tasks()

    incomplete_todos = sum(1 for task in tasks if
            isinstance(task, habitrpg.Todo) and not task.completed)
    reduce_task = next((task for task in tasks if task.title == TASK_NAME and
                            not task.completed),
                       None)

    notes = '{:%A %I:%M %p}: {} tasks'.format(datetime.now(TZ),
                                              incomplete_todos)
    if incomplete_todos > MAX_TODOS and reduce_task is None:
        habitrpg.Todo.new(user, title=TASK_NAME, notes=notes)
    elif incomplete_todos <= (CLEAR_THRESHOLD + 1) and reduce_task is not None:
        reduce_task.complete()
    elif reduce_task is not None:
        reduce_task.update(notes=notes)
