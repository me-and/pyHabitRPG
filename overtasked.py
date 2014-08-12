#!/usr/bin/env python3
import os.path

import habitrpg

LOGIN_DETAIL_FILE = '~/.habitrpg'
TASK_NAME = 'Cut the todo list down to ≤15 tasks'

if __name__ == '__main__':
    with open(os.path.expanduser(LOGIN_DETAIL_FILE)) as login_file:
        user_id = login_file.readline().strip()
        api_token = login_file.readline().strip()

    hrpg = habitrpg.HabitRPG(user_id, api_token)
    tasks = hrpg.tasks()

    if (sum(1 for task in tasks if isinstance(task, habitrpg.Todo) and
                not task.completed) > 20 and
            next((task for task in tasks if task.text == TASK_NAME), None)
                is None):
        hrpg.create_task('todo', TASK_NAME)
