import json
import os.path
import datetime
from csv import DictReader
from io import StringIO

from requests import Session

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
        self.session = Session()

    def __eq__(self, other):
        try:
            return self.uri == other.uri
        except AttributeError:
            return NotImplemented

    def __hash__(self):
        return hash(self.uri)

    def __repr__(self):
        if self.uri == DEFAULT_API_BASE_URI:
            return '{}()'.format(self.__class__.__name__)
        else:
            return '{}({!r})'.format(self.__class__.__name__, self.uri)

    def api_request(self, method, path, headers=None, body=None, params=None,
                    raise_status=True, decode=True):
        if body is not None:
            body = json.dumps(body)
            if headers is None:
                headers = {'content-type': 'application/json'}
            else:
                headers['content-type'] = 'application/json'

        response = self.session.request(method,
                                        '{}/{}'.format(self.uri, path),
                                        headers=headers,
                                        data=body,
                                        params=params)

        if raise_status:
            response.raise_for_status()

        if decode:
            content_type = response.headers['content-type']
            if content_type.startswith('application/json;'):
                return response.json()
            elif content_type.startswith('text/csv;'):
                stream = StringIO(response.text)  # Needed for csv.DictReader
                return DictReader(stream)
            elif content_type == 'text/html':
                return response.text
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
        self.tasks_populated = False
        self.tags_populated = False

    def __eq__(self, other):
        try:
            return (self.hrpg == other.hrpg and self.user_id == other.user_id
                    and self.api_token == other.api_token)
        except AttributeError:
            return NotImplemented

    def __hash__(self):
        return hash((self.hrpg, self.user_id, self.api_token))

    def __repr__(self):
        return '{}({!r}, {!r}, {!r})'.format(self.__class__.__name__,
                                             self.hrpg,
                                             self.user_id,
                                             self.api_token)

    @classmethod
    def from_file(cls, hrpg=None, file_path=DEFAULT_LOGIN_FILE):
        if hrpg is None:
            hrpg = HabitRPG()
        with open(file_path) as login_file:
            user_id = login_file.readline().strip()
            api_token = login_file.readline().strip()
        return cls(hrpg, user_id, api_token)

    def api_request(self, method, path, body=None, params=None,
                    raise_status=True, decode=True):
        headers = {'x-api-user': self.user_id,
                   'x-api-key': self.api_token}
        return self.hrpg.api_request(method, path, headers, body, params,
                                     raise_status, decode)

    def history(self):
        return self.api_request('GET', 'export/history')

    def fetch(self):
        response = self.api_request('GET', 'user')

        self.habits = [Habit.create_from_api_response(self, task_data) for
                task_data in response['habits']]
        self.dailies = [Daily.create_from_api_response(self, task_data) for
                task_data in response['dailys']]
        self.todos = [Todo.create_from_api_response(self, task_data) for
                task_data in response['todos']]
        self.rewards = [Reward.create_from_api_response(self, task_data) for
                task_data in response['rewards']]
        self.tasks_populated = True

        self.populate_tags_from_api_response(response['tags'])

    def populate_tags_from_api_response(self, api_response):
        self.tags = [Tag.create_from_api_response(self, tag_data) for
                tag_data in api_response]
        self.tags_populated = True

    def task_from_api_response(self, api_response):
        task_type = api_response['type']
        for task_class in Habit, Daily, Todo, Reward:
            if task_type == task_class.task_type:
                return task_class.create_from_api_response(self, api_response)
        raise KeyError(task_type)  # No match

    def fetch_tasks(self):
        tasks = [self.task_from_api_response(task_data) for task_data in
                self.api_request('GET', 'user/tasks')]
        self.habits = []
        self.dailies = []
        self.todos = []
        self.rewards = []
        for task in tasks:
            if isinstance(task, Habit):
                self.habits.append(task)
            elif isinstance(task, Daily):
                self.dailies.append(task)
            elif isinstance(task, Todo):
                self.todos.append(task)
            elif isinstance(task, Reward):
                self.rewards.append(task)
            else:
                raise ValueError('Unexpected task {!r}'.format(task))
        self.tasks_populated = True

class UserPlusIDMixin(object):
    def __init__(self, user, id_code):
        self.user = user
        self.id_code = id_code
        self.populated = False

    def __eq__(self, other):
        try:
            return self.user == other.user and self.id_code == other.id_code
        except AttributeError:
            return NotImplemented

    def __hash__(self):
        return hash((self.user, self.id_code))

    def __repr__(self):
        return '<{} id {!r}>'.format(self.__class__.__name__,
                                     self.id_code)

    @classmethod
    def create_from_api_response(cls, user, api_response):
        inst = cls(user, api_response['id'])
        inst.populate_from_api_response(api_response)
        return inst

class Task(UserPlusIDMixin):
    def __repr__(self):
        if self.populated:
            return '<{} id {!r} title {!r}>'.format(self.__class__.__name__,
                                                    self.id_code,
                                                    self.title)
        else:
            return super().__repr__()

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
    def new(cls, user, *, request=None, title=None, notes=None, value=None,
            priority=None, tags=None):
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
        if tags is not None:
            request['tags'] = {}
            for tag in tags:
                request['tags'][tag.id_code] = True

        response = user.api_request('POST', 'user/tasks', request)
        return cls.create_from_api_response(user, response)

    def update(self, request=None, title=None, notes=None, value=None,
               priority=None, tags=None):
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
        if tags is not None:
            request['tags'] = {}
            for tag in tags:
                request['tags'][tag.id_code] = True

        response = self.user.api_request(
                'PUT', 'user/tasks/{}'.format(self.id_code), request)
        self.populate_from_api_response(response)

    def delete(self):
        # After calling this, remember to call User.fetch_tasks() if the task
        # lists need updating.
        self.user.api_request('DELETE', 'user/tasks/{}'.format(self.id_code))

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
    def new(cls, user, *, request=None, completed=None, **kwargs):
        if request is None:
            request = {}
        if completed is not None:
            request['completed'] = completed
        return super().new(user, request=request, **kwargs)

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
        # Both 'checklist' and 'collapseChecklist' may be missing from the API
        # response.  We test explicitly for the former case, and in the latter
        # case just use `dict.get()` to pick it up, since that will return
        # `None` if the element isn't in the dictionary.
        if 'checklist' in api_response:
            self.checklist = [CheckItem.create_from_api_response(self.user,
                                                                 self,
                                                                 check_data)
                    for check_data in api_response['checklist']]
        else:
            self.checklist = []
        self.collapse_checklist = api_response.get('collapseChecklist')
        super().populate_from_api_response(api_response)

    @classmethod
    def new(cls, user, *, request=None, checklist=None, **kwargs):
        if request is None:
            request = {}
        if checklist is not None:
            request['checklist'] = []
            for text, completed in checklist:
                request['checklist'].append({'text': text,
                                             'completed': completed})
        return super().new(user, request=request, **kwargs)

    def update(self, request=None, checklist=None, **kwargs):
        if request is None:
            request = {}
        if checklist is not None:
            request['checklist'] = []
            for text, completed in checklist:
                request['checklist'].append({'text': text,
                                             'completed': completed})
        return super().update(request=request, **kwargs)

    @classmethod
    def create_from_api_response(cls, user, api_response):
        task = cls(user, api_response['id'])
        if 'checklist' in api_response:
            for check_item in api_response['checklist']:
                if 'id' not in check_item:
                    # There's a checklist item that doesn't have an ID.  This
                    # appears to happen on newly created tasks, but re-fetching
                    # the task rather than relying on the original API request
                    # will work fine.
                    task.fetch()
                    return task
        task.populate_from_api_response(api_response)
        return task

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
    def new(cls, user, *, request=None, can_up=None, can_down=None, **kwargs):
        if request is None:
            request = {}
        if can_up is not None:
            request['up'] = can_up
        if can_down is not None:
            request['down'] = can_down
        return super().new(user, request=request, **kwargs)

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

    @classmethod
    def new(cls, user, *, request=None, due_date=None, date_completed=None,
            **kwargs):
        if request is None:
            request = {}
        if due_date is not None:
            # TODO: Check the behaviour here emulates the website's behaviour
            # with regard to timezones.
            request['date'] = due_date.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        if date_completed is not None:
            request['dateCompleted'] = (
                date_completed.strftime('%Y-%m-%dT%H:%M:%S.%fZ'))
        return super().new(user, request=request, **kwargs)

    def update(self, request=None, due_date=None, date_completed=None,
               **kwargs):
        if request is None:
            request = {}
        if due_date is not None:
            # TODO: Check the behaviour here emulates the website's behaviour
            # with regard to timezones.
            #
            # TODO: This code is probably substantive enough to commonalize it
            # with the code from Todo.new().  Although that probably applies to
            # all the new/update methods, really.
            request['date'] = due_date.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        if date_completed is not None:
            request['dateCompleted'] = (
                date_completed.strftime('%Y-%m-%dT%H:%M:%S.%fZ'))
        return super().update(request, **kwargs)

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

    def __eq__(self, other):
        try:
            return (self.timestamp == other.timestamp and
                    self.value == other.value)
        except AttributeError:
            return NotImplemented

    def __hash__(self):
        return hash((self.timestamp, self.value))

    def __repr__(self):
        return '{}({!r}, {!r})'.format(self.__class__.__name__,
                                       self.timestamp,
                                       self.value)

    @classmethod
    def create_from_api_response(cls, api_response):
        return cls(
            datetime.datetime.fromtimestamp(api_response['date'] / 1000),
            api_response['value'])

class Tag(UserPlusIDMixin):
    def __repr__(self):
        if self.populated:
            return '<{} id {!r} name {!r}>'.format(self.__class__.__name__,
                                                    self.id_code,
                                                    self.name)
        else:
            return super().__repr__()

    def populate_from_api_response(self, api_response):
        self.name = api_response.get('name')  # May not exist!
        try:
            challenge = api_response['challenge']
        except KeyError:  # Not on response so no challenge
            self.challenge = False
        else:
            if challenge == 'true':
                self.challenge = True
            else:
                raise ValueError('Unexpected challenge value {!r}'
                        .format(challenge))
        self.populated = True

    def fetch(self, force_update=False):
        # There's no good way to just fetch this tag, so make sure `self.user`
        # has the tag list and populate this instance's data based on that tag
        # list.
        if force_update or not self.user.tags_populated:
            self.user.fetch()
        for tag in self.user.tags:
            if self.id_code == tag.id_code:
                self.name = tag.name
                self.challenge = tag.challenge
                break
        else:
            raise RuntimeError('Tag with ID {!r} not found'
                    .format(self.id_code))
        self.populated = True

    @classmethod
    def new(cls, user, name=None):
        request = {}
        if name is not None:
            request['name'] = name
        response = user.api_request('POST', 'user/tags', request)

        # The API response is a list of all the tags.  It appears the last tag
        # is always the one we just created.
        user.populate_tags_from_api_response(response)
        tag = user.tags[-1]
        return tag

    def delete(self):
        response = self.user.api_request('DELETE',
                                         'user/tags/{}'.format(self.id_code))
        user.populate_tags_from_api_response(response)

class CheckItem(UserPlusIDMixin):
    def __init__(self, user, task, id_code):
        self.task = task
        super().__init__(user, id_code)

    def __eq__(self, other):
        try:
            return (self.user == other.user and self.task == other.task and
                    self.id_code == other.id_code)
        except AttributeError:
            return NotImplemented

    def __hash__(self):
        return hash((self.user, self.task, self.id_code))

    def __repr__(self):
        if self.populated:
            return '<{} id {!r} text {!r}>'.format(self.__class__.__name__,
                                                   self.id_code,
                                                   self.text)
        else:
            return super().__repr__()

    @classmethod
    def create_from_api_response(cls, user, task, api_response):
        inst = cls(user, task, api_response['id'])
        inst.populate_from_api_response(api_response)
        return inst

    def populate_from_api_response(self, api_response):
        self.text = api_response['text']
        self.completed = api_response['completed']
        self.populated = True

class Group(UserPlusIDMixin):
    def send_chat(self, message):
        self.user.api_request('POST', 'groups/{}/chat'.format(self.id_code),
                              params={'message': message})

class Party(Group):
    def __init__(self, user):
        super().__init__(user=user, id_code='party')
