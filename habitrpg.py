import json
import os.path
import datetime
from csv import DictReader
from io import StringIO

import requests

DEFAULT_API_BASE_URI = 'https://habitrpg.com/api/v2'
DEFAULT_LOGIN_FILE = os.path.expanduser(os.path.join('~', '.habitrpg'))

def parse_possible_timestamp(timestamp):
    if timestamp is None:
        return None
    else:
        return (datetime.datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S.%fZ')
                    .replace(tzinfo=datetime.timezone.utc))

class HabitRPG(object):
    def __init__(self, uri=DEFAULT_API_BASE_URI):
        self.uri = uri

    def api_request(self, method, path, headers=None, body=None, decode=True):
        if body is not None:
            body = json.dumps(body)
            try:
                headers['content-type'] = 'application/json'
            except TypeError:  # headers is None
                headers = {'content-type': 'application/json'}

        response = requests.request(method,
                                    '{}/{}'.format(self.uri, path),
                                    headers=headers,
                                    data=body)

        response.raise_for_status()

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

    def status(self):
        return self.api_request('GET', 'status')['status']

    def content(self, language=None):
        if language is not None:
            body = {'language': language}
        else:
            body = None
        return self.api_request('GET', 'content', body=body)

    def user_model(self):
        return self.api_request('GET', 'content/paths')

class User(object):
    def __init__(self, hrpg, user_id, api_token):
        self.hrpg = hrpg
        self.user_id = user_id
        self.api_token = api_token

    @classmethod
    def from_file(cls, hrpg=None, file_path=DEFAULT_LOGIN_FILE):
        if hrpg is None:
            hrpg = HabitRPG()
        with open(file_path) as login_file:
            user_id = login_file.readline().strip()
            api_token = login_file.readline().strip()
        return cls(hrpg, user_id, api_token)

    def api_request(self, method, path, body=None, decode=True):
        headers = {'x-api-user': self.user_id,
                   'x-api-key': self.api_token}
        return self.hrpg.api_request(method, path, headers, body, decode)

    def history(self):
        return self.api_request('GET', 'export/history')

    def task_from_api_response(self, api_response):
        task_type = api_response['type']
        for task_class in Habit, Daily, Todo, Reward:
            if task_type == task_class.task_type:
                return task_class.create_from_api_response(self, api_response)
        raise KeyError(task_type)  # No match

    def tasks(self):
        return [self.task_from_api_response(task_data) for task_data in
                self.api_request('GET', 'user/tasks')]

class Task(object):
    def __init__(self, user, id_code):
        self.user = user
        self.id_code = id_code
        self.populated = False

    def fetch(self):
        task_data = self.user.api_request('GET',
                                          'user/tasks/{}'.format(self.id_code))
        self.populate_from_api_response(task_data)

    def populate_from_api_response(self, api_response):
        # Some elements may be missing from the API response; use `dict.get()`
        # to pick up those, since that will return `None` if the element isn't
        # in the dictionary.
        self.title = api_response['text']
        self.notes = api_response['notes']
        self.tags = api_response.get('tags')  # TODO Parse this
        self.date_created = parse_possible_timestamp(
                api_response['dateCreated'])
        self.value = api_response['value']
        self.priority = api_response['priority']
        self.attribute = api_response['attribute']
        self.challenge = api_response.get('challenge')  # TODO Parse this
        self.populated = True

    @classmethod
    def create_from_api_response(cls, user, api_response):
        task = cls(user, api_response['id'])
        task.populate_from_api_response(api_response)
        return task

    @classmethod
    def new(cls, user, request=None, title=None, notes=None, value=None,
            priority=None):
        if request is None:
            request = {}
        request['type'] = cls.task_type
        if title is not None:
            request['text'] = title
        if notes is not None:
            request['notes'] = notes
        if value is not None:
            request['value'] = value
        if priority is not None:
            request['priority'] = priority

        response = user.api_request('POST', 'user/tasks', request)
        return cls.create_from_api_response(user, response)

    def update(self, request=None, title=None, notes=None, value=None,
               priority=None):
        if request is None:
            request = {}
        if title is not None:
            request['text'] = title
        if notes is not None:
            request['notes'] = notes
        if value is not None:
            request['value'] = value
        if priority is not None:
            request['priority'] = priority

        response = self.user.api_request(
                'PUT', 'user/tasks/{}'.format(self.id_code), request)
        self.populate_from_api_response(response)

    def _up(self, update=False):
        self.user.api_request('POST', 'user/tasks/{}/up'.format(self.id_code))
        if update:
            self.fetch()

    def _down(self, update=False):
        self.user.api_request('POST',
                              'user/tasks/{}/down'.format(self.id_code))
        if update:
            self.fetch()

class CompletableTaskMixin(object):
    def populate_from_api_response(self, api_response):
        self.completed = api_response['completed']
        super().populate_from_api_response(api_response)

    @classmethod
    def new(cls, user, request=None, completed=None, **kwargs):
        if request is None:
            request = {}
        if completed is not None:
            request['completed'] = completed
        return super().new(user, request, **kwargs)

    def update(self, request=None, completed=None, **kwargs):
        if request is None:
            request = {}
        if completed is not None:
            request['completed'] = completed
        return super().update(request, **kwargs)

    def complete(self, *args, **kwargs):
        return self._up(*args, **kwargs)
    def uncomplete(self):
        return self._down(*args, **kwargs)

class ChecklistTaskMixin(object):
    def populate_from_api_response(self, api_response):
        # Some elements may be missing from the API response; use `dict.get()`
        # to pick up those, since that will return `None` if the element isn't
        # in the dictionary.
        self.checklist = api_response.get('checklist')
        self.collapse_checklist = api_response.get('collapseChecklist')
        super().populate_from_api_response(api_response)

class HistoryTaskMixin(object):
    def populate_from_api_response(self, api_response):
        self.history = [HistoryStamp.create_from_api_response(hist_item) for
                hist_item in api_response['history']]
        super().populate_from_api_response(api_response)

class Habit(HistoryTaskMixin, Task):
    task_type = 'habit'

    def populate_from_api_response(self, api_response):
        self.can_plus = api_response['up']
        self.can_minus = api_response['down']
        super().populate_from_api_response(api_response)

    @classmethod
    def new(cls, user, request=None, can_up=None, can_down=None, **kwargs):
        if request is None:
            request = {}
        if can_up is not None:
            request['up'] = can_up
        if can_down is not None:
            request['down'] = can_down
        return super().new(user, request, **kwargs)

    def update(self, request=None, can_up=None, can_down=None, **kwargs):
        if request is None:
            request = {}
        if can_up is not None:
            request['up'] = can_up
        if can_down is not None:
            request['down'] = can_down
        return super().update(request, **kwargs)

    def up(self, *args, **kwargs):
        return self._up(*args, **kwargs)
    def down(self):
        return self._down(*args, **kwargs)

class Daily(CompletableTaskMixin, ChecklistTaskMixin, HistoryTaskMixin, Task):
    task_type = 'daily'
    def populate_from_api_response(self, api_response):
        self.streak = api_response['streak']
        self.repeat = api_response['repeat']  # TODO Parse this
        super().populate_from_api_response(api_response)

class Todo(CompletableTaskMixin, ChecklistTaskMixin, Task):
    task_type = 'todo'
    def populate_from_api_response(self, api_response):
        # Some elements may be missing from the API response; use `dict.get()`
        # to pick up those, since that will return `None` if the element isn't
        # in the dictionary.
        self.due_date = parse_possible_timestamp(api_response.get('date'))
        self.date_completed = parse_possible_timestamp(
                api_response.get('dateCompleted'))
        super().populate_from_api_response(api_response)

class Reward(Task):
    task_type = 'reward'
    def buy(self, *args, **kwargs):
        return self._up(*args, **kwargs)

class HistoryStamp(object):
    def __init__(self, timestamp, value):
        self.timestamp = timestamp
        self.value = value

    @classmethod
    def create_from_api_response(cls, api_response):
        return cls(
            datetime.datetime.fromtimestamp(api_response['date'] / 1000),
            api_response['value'])
