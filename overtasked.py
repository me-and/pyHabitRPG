#!/usr/bin/env python3
from datetime import datetime
import sys

from pytz import timezone

import habitrpg

MAX_TODOS = 20
CLEAR_THRESHOLD = 18
TASK_NAME = 'Cut the todo list down to ≤{} tasks'.format(CLEAR_THRESHOLD)
TZ = timezone('Europe/London')

def find_incomplete_todos(todos):
    return [todo for todo in todos if not todo.completed]

def find_reduce_task(todos):
    try:
        return next((todo for todo in todos if todo.title == TASK_NAME))
    except StopIteration:  # No such task
        return None

def create_update_reduce_task(reduce_task, num_todos, print_count=True):
    notes = '{:%A %I:%M %p}: {} tasks'.format(datetime.now(TZ), num_todos)
    if print_count and sys.stdout.isatty():
        print(notes)

    if num_todos > MAX_TODOS and reduce_task is None:
        habitrpg.Todo.new(user, title=TASK_NAME, notes=notes)
    elif num_todos <= (CLEAR_THRESHOLD + 1) and reduce_task is not None:
        reduce_task.complete()
    elif reduce_task is not None:
        reduce_task.update(notes=notes)

if __name__ == '__main__':
    user = habitrpg.User.from_file()
    user.fetch_tasks()

    incomplete_todos = find_incomplete_todos(user.todos)
    reduce_task = find_reduce_task(incomplete_todos)

    create_update_reduce_task(reduce_task, len(incomplete_todos))
