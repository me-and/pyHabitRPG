#!/usr/bin/env python3
"""Fix dailies that have failed to be reset during a cron run.

Run this script if you've been affected by the ["Dailies Remain Checked"][DRC]
bug to reset all of your dailies and their checklist items to be uncompleted,
without affecting the streak scores or any of your character's statistics.

[DRC]: http://habitrpg.wikia.com/wiki/Known_Bugs#Dailies_Remain_Checked

"""

import habitrpg

if __name__ == '__main__':
    user = habitrpg.User.from_file()
    user.fetch_tasks()
    for daily in user.dailies:
        daily.update(completed=False,
                     checklist=[(c.text, False) for c in daily.checklist])
