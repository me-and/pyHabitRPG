#!/usr/bin/env python3
import os.path

import pyhrpg

LOGIN_DETAIL_FILE = '~/.habitrpg'
TASK_NAME = 'Cut the todo list down to ≤15 tasks'

if __name__ == '__main__':
    with open(os.path.expanduser(LOGIN_DETAIL_FILE)) as login_file:
        user_id = login_file.readline().strip()
        api_token = login_file.readline().strip()

    habitrpg = pyhrpg.HabitRPG(user_id, api_token)
    tasks = habitrpg.tasks()

    if (sum(1 for task in tasks if
                isinstance(task, pyhrpg.Todo) and not task.completed) > 20 and
            next((task for task in tasks if task.text == TASK_NAME), None)
                is None):
        habitrpg.create_task('todo', TASK_NAME)
