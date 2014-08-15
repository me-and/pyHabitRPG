import json
import os.path
import datetime

import requests

API_BASE_URI = 'https://habitrpg.com/api/v2'
DEFAULT_LOGIN_FILE = os.path.expanduser('~/.habitrpg')

def parse_timestamp(string):
    if string is None:
        return None
    else:
        return (datetime.datetime.strptime(string, '%Y-%m-%dT%H:%M:%S.%fZ')
                    .replace(tzinfo=datetime.timezone.utc))

class HabitRPG(object):
    def __init__(self, user_id, api_token):
        self.user_id = user_id
        self.api_token = api_token

    @classmethod
    def login_from_file(cls, file_name=DEFAULT_LOGIN_FILE):
        with open(file_name) as login_file:
            user_id = login_file.readline().strip()
            api_token = login_file.readline().strip()
        return cls(user_id, api_token)

    @staticmethod
    def _api_request(method, path, headers=None, body=None):
        if body is not None:
            body = json.dumps(body)
            try:
                headers['content-type'] = 'application/json'
            except TypeError:  # headers is None
                headers = {'content-type': 'application/json'}

        response = requests.request(method,
                                    '{}/{}'.format(API_BASE_URI, path),
                                    headers=headers,
                                    data=body)

        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            print(response.json()['err'])
            raise

        return response.json()

    def _authed_api_request(self, method, path, body=None):
        headers = {'x-api-user': self.user_id,
                   'x-api-key': self.api_token}
        return self._api_request(method, path, headers, body)

    @classmethod
    def status(cls):
        return cls._api_request('GET', 'status')['status']

    def tasks(self):
        return list(map(lambda x: Task.new_from_api_response(self, x),
                        self._authed_api_request('GET', 'user/tasks')))

    def create_task(self, task_type, text=None):
        data = {'type': task_type}
        if text is not None:
            data['text'] = text
        return Task.new_from_api_response(
                self,
                self._authed_api_request('POST', 'user/tasks', data))

class Task(object):
    def __init__(self,
                 habitrpg,
                 id_code,
                 text,
                 notes,
                 tags,
                 value,
                 priority,
                 date_created,
                 attribute,
                 challenge):
        self.habitrpg = habitrpg
        self.id_code = id_code
        self.text = text
        self.notes = notes
        self.tags = tags
        self.value = value
        self.priority = priority
        self.date_created = date_created
        self.attribute = attribute
        self.challenge = challenge

    @staticmethod
    def new_from_api_response(habitrpg, api_response):
        for task_class in Habit, Daily, Todo, Reward:
            if api_response['type'] == task_class.task_type:
                return task_class.new_from_api_response(habitrpg, api_response)
        raise KeyError(api_response['type'])  # Nothing matched

class Habit(Task):
    task_type = 'habit'

    def __init__(self, can_up, can_down, history, **kwargs):
        self.can_up = can_up
        self.can_down = can_down
        self.history = history
        super().__init__(**kwargs)

    @classmethod
    def new_from_api_response(cls, habitrpg, api_response):
        return cls(habitrpg=habitrpg,
                   can_up=api_response['up'],
                   can_down=api_response['down'],
                   history=list(map(HistoryStamp.new_from_api_response,
                                    api_response['history'])),
                   id_code=api_response['id'],
                   text=api_response['text'],
                   notes=api_response['notes'],
                   tags=api_response.get('tags'),  # TODO Parse this
                   value=api_response['value'],
                   priority=api_response['priority'],
                   date_created=parse_timestamp(api_response['dateCreated']),
                   attribute=api_response['attribute'],
                   challenge=api_response.get('challenge'))  # TODO Parse this

    def score_up(self):
        return self.habitrpg._authed_api_request('POST',
                                                 'user/tasks/{}/up'
                                                     .format(self.id_code))
    def score_down(self):
        return self.habitrpg._authed_api_request('POST',
                                                 'user/tasks/{}/down'
                                                     .format(self.id_code))

class Daily(Task):
    task_type = 'daily'

    def __init__(self,
                 completed,
                 repeat,
                 checklist,
                 collapse_checklist,
                 streak,
                 history,
                 **kwargs):
        self.completed = completed
        self.repeat = repeat
        self.checklist = checklist
        self.collapse_checklist = collapse_checklist
        self.streak = streak
        self.history = history
        super().__init__(**kwargs)

    @classmethod
    def new_from_api_response(cls, habitrpg, api_response):
        return cls(habitrpg=habitrpg,
                   completed=api_response['completed'],
                   repeat=api_response['repeat'],  # TODO Parse this
                   checklist=api_response.get('checklist'),  # TODO Parse this
                   collapse_checklist=api_response.get('collapseChecklist'),
                   streak=api_response['streak'],
                   history=list(map(HistoryStamp.new_from_api_response,
                                    api_response['history'])),
                   id_code=api_response['id'],
                   text=api_response['text'],
                   notes=api_response['notes'],
                   tags=api_response.get('tags'),  # TODO Parse this
                   value=api_response['value'],
                   priority=api_response['priority'],
                   date_created=parse_timestamp(api_response['dateCreated']),
                   attribute=api_response['attribute'],
                   challenge=api_response.get('challenge'))  # TODO Parse this

class Todo(Task):
    task_type = 'todo'

    def __init__(self,
                 completed,
                 due_date,
                 date_completed,
                 checklist,
                 collapse_checklist,
                 **kwargs):
        self.completed = completed
        self.due_date = due_date
        self.date_completed = date_completed
        self.collapse_checklist = collapse_checklist
        super().__init__(**kwargs)

    @classmethod
    def new_from_api_response(cls, habitrpg, api_response):
        return cls(
            habitrpg=habitrpg,
            completed=api_response['completed'],
            due_date=parse_timestamp(api_response.get('date')),
            date_completed=parse_timestamp(api_response.get('dateCompleted')),
            checklist=api_response.get('checklist'),  # TODO Parse this
            collapse_checklist=api_response.get('collapseChecklist'),
            id_code=api_response['id'],
            text=api_response['text'],
            notes=api_response['notes'],
            tags=api_response.get('tags'),  # TODO Parse this
            value=api_response['value'],
            priority=api_response['priority'],
            date_created=parse_timestamp(api_response['dateCreated']),
            attribute=api_response['attribute'],
            challenge=api_response.get('challenge'))  # TODO Parse this

class Reward(Task):
    task_type = 'reward'

    @classmethod
    def new_from_api_response(cls, habitrpg, api_response):
        return cls(habitrpg=habitrpg,
                   id_code=api_response['id'],
                   text=api_response['text'],
                   notes=api_response['notes'],
                   tags=api_response.get('tags'),  # TODO Parse this
                   value=api_response['value'],
                   priority=api_response['priority'],
                   date_created=parse_timestamp(api_response['dateCreated']),
                   attribute=api_response['attribute'],
                   challenge=api_response.get('challenge'))  # TODO Parse this

class HistoryStamp(object):
    def __init__(self, timestamp, value):
        self.timestamp = timestamp
        self.value = value

    @classmethod
    def new_from_api_response(cls, api_response):
        return cls(
            datetime.datetime.fromtimestamp(api_response['date'] / 1000),
            api_response['value'])
