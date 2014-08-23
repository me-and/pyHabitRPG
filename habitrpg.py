import json
import os.path
import datetime
from csv import DictReader
from io import StringIO

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
    def _api_request(method, path, headers=None, body=None, decode=True):
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

        if decode:
            content_type = response.headers['content-type']
            if content_type.startswith('application/json;'):
                return response.json()
            elif content_type.startswith('text/csv;'):
                stream = StringIO(response.text)  # Needed for csv.DictReader
                return DictReader(stream)
            else:
                raise RuntimeError('Content type "{}" unrecognized'
                        .format(content_type))
        else:
            return response

    def _authed_api_request(self, method, path, body=None, decode=True):
        headers = {'x-api-user': self.user_id,
                   'x-api-key': self.api_token}
        return self._api_request(method, path, headers, body, decode)

    @classmethod
    def status(cls):
        return cls._api_request('GET', 'status')['status']

    @classmethod
    def content(cls, language=None):
        if language is not None:
            body = {'language': language}
        else:
            body = None
        return cls._api_request('GET', 'content', body=body)

    @classmethod
    def user_model(cls):
        return cls._api_request('GET', 'content/paths')

    def tasks(self):
        return list(map(lambda x: Task.new_from_api_response(self, x),
                        self._authed_api_request('GET', 'user/tasks')))

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

    @classmethod
    def create(cls, habitrpg, request=None, text=None, notes=None, value=None,
               priority=None):
        if request is None:
            request = {}
        request['type'] = cls.task_type
        if text is not None:
            request['text'] = text
        if notes is not None:
            request['notes'] = notes
        if value is not None:
            request['value'] = value
        if priority is not None:
            request['priority'] = priority

        response = habitrpg._authed_api_request('POST', 'user/tasks', request)
        return cls.new_from_api_response(habitrpg, response)

    def update(self, request=None, task_type=None, text=None, notes=None,
               value=None, priority=None):
        if request is None:
            request = {}
        if task_type is not None:
            request['type'] = task_type
        if text is not None:
            request['text'] = text
        if notes is not None:
            request['notes'] = notes
        if value is not None:
            request['value'] = value
        if priority is not None:
            request['priority'] = priority

        response = self.habitrpg._authed_api_request(
                'PUT', 'user/tasks/{}'.format(self.id_code), request)
        # TODO Update self

    def score_up(self):
        return self.habitrpg._authed_api_request('POST',
                                                 'user/tasks/{}/up'
                                                     .format(self.id_code))
    def score_down(self):
        return self.habitrpg._authed_api_request('POST',
                                                 'user/tasks/{}/down'
                                                     .format(self.id_code))

class CompletableTaskMixin(object):
    def complete(self):
        return self.score_up()
    def uncomplete(self):
        return self.score_down()

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

    @classmethod
    def create(cls, habitrpg, can_up=None, can_down=None, **kwargs):
        request = {}
        if can_up is not None:
            request['up'] = can_up
        if can_down is not None:
            request['down'] = can_down
        return super().create(habitrpg, request, **kwargs)

class Daily(Task, CompletableTaskMixin):
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

    @classmethod
    def create(cls, habitrpg, completed=None, **kwargs):
        request = {}
        if completed is not None:
            request['completed'] = completed
        return super().create(habitrpg, request, **kwargs)

class Todo(Task, CompletableTaskMixin):
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

    @classmethod
    def create(cls, habitrpg, completed=None, **kwargs):
        request = {}
        if completed is not None:
            request['completed'] = completed
        return super().create(habitrpg, request, **kwargs)

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
