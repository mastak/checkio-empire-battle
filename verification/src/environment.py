from tornado import gen

from checkio_referee.environment.controller import EnvironmentsController
from checkio_referee.environment.client import EnvironmentClient


class BattleEnvironmentClient(EnvironmentClient):

    @gen.coroutine
    def select_result(self, data):
        self.write({
            'status': 200,
            'data': data
        })

    @gen.coroutine
    def confirm(self):
        self.write({
            'status': 200
        })

    @gen.coroutine
    def bad_action(self, error=None):
        message = {
            'status': 400,
        }
        if error is not None:
            message['data'] = {
                'error': str(error)
            }
        self.write(message)

    @gen.coroutine
    def send_event(self, lookup_key, data):
        self.write({
            'action': 'event',
            'lookup_key': lookup_key,
            'data': data
        })


class BattleEnvironmentsController(EnvironmentsController):
    ENVIRONMENT_CLIENT_CLS = BattleEnvironmentClient
