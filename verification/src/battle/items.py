from tornado import gen

from .item_actions import ItemActions
from .item_actions.exceptions import ActionValidateError
from .terms import PLAYER, ROLE, ATTRIBUTE, ACTION, STATUS


class Item(object):
    ITEMS_COUNT = 0

    @classmethod
    def generate_id(cls):
        cls.ITEMS_COUNT += 1
        return cls.ITEMS_COUNT


class FightItem(Item):
    """
        class for a single item in the fight.
        It can be a simple building, a defence building,
        a unit that move and attack other buildings
    """
    HANDLERS = None
    ACTIONS = None
    SELECT_HANDLERS = None

    def __init__(self, item_data, player, fight_handler):
        self.init_handlers()
        self.id = self.generate_id()
        self.player = player  # dict, data about the player who owns this Item
        # available types: center, unit, tower, building, obstacle
        self.role = item_data.get(ATTRIBUTE.ROLE)  # type of current Item

        self.item_type = item_data.get(ATTRIBUTE.ITEM_TYPE)
        self.alias = item_data.get(ATTRIBUTE.ALIAS)
        self.level = item_data.get(ATTRIBUTE.LEVEL)
        self.tile_position = item_data.get(ATTRIBUTE.TILE_POSITION)
        self.item_status = item_data.get(ATTRIBUTE.ITEM_STATUS)

        self.start_hit_points = item_data.get(ATTRIBUTE.HIT_POINTS)
        self.hit_points = item_data.get(ATTRIBUTE.HIT_POINTS)
        self.size = item_data.get(ATTRIBUTE.SIZE, 0)
        self.base_size = item_data.get(ATTRIBUTE.BASE_SIZE, 0)
        self.speed = item_data.get(ATTRIBUTE.SPEED)

        self.coordinates = item_data.get(ATTRIBUTE.COORDINATES)  # list of two

        self.rate_of_fire = item_data.get(ATTRIBUTE.RATE_OF_FIRE)
        self.damage_per_shot = item_data.get(ATTRIBUTE.DAMAGE_PER_SHOT)
        self.firing_range = item_data.get(ATTRIBUTE.FIRING_RANGE)
        self.area_damage_per_shot = item_data.get(ATTRIBUTE.AREA_DAMAGE_PER_SHOT, 0)
        self.area_damage_radius = item_data.get(ATTRIBUTE.AREA_DAMAGE_RADIUS, 0)

        # a current command that was send from code
        self.action = item_data.get(ACTION.REQUEST_NAME)
        self.charging = 0

        self._fight_handler = fight_handler  # object of FightHandler
        self.code = self._fight_handler.codes.get(item_data.get(ATTRIBUTE.OPERATING_CODE))
        self._initial = item_data
        self._env = None  # ??
        self._state = None  # dict of current FightItem state
        # every state has a key "action"
        # {'action': 'idle'}
        # {'action': 'dead'}
        self._actions_handlers = ItemActions.get_factory(self, fight_handler=fight_handler)
        self.set_state_idle()

    @property
    def is_dead(self):
        return self.hit_points <= 0

    @property
    def is_obstacle(self):
        return self.role == "obstacle"

    @property
    def info(self):
        # DEPRECATED
        return {
            ATTRIBUTE.ID: self.id,
            ATTRIBUTE.PLAYER_ID: self.player["id"],
            ATTRIBUTE.ROLE: self.role,
            ATTRIBUTE.HIT_POINTS: self.hit_points,
            ATTRIBUTE.SIZE: self.size,
            ATTRIBUTE.SPEED: self.speed,
            ATTRIBUTE.COORDINATES: self.coordinates,
            ATTRIBUTE.RATE_OF_FIRE: self.rate_of_fire,
            ATTRIBUTE.DAMAGE_PER_SHOT: self.damage_per_shot,
            ATTRIBUTE.AREA_DAMAGE_PER_SHOT: self.area_damage_per_shot,
            ATTRIBUTE.AREA_DAMAGE_RADIUS: self.area_damage_radius,
            ATTRIBUTE.FIRING_RANGE: self.firing_range,
            ACTION.REQUEST_NAME: self.action,
            # TODO State should be reworked
            'state': self._state
        }

    def init_handlers(self):
        """
            there are only 3 kind of actions that can be send from FightItem to Referee
            select - to ask data from system
            set_action - to command unit to do
            subscribe - to subscribe on some event
        """
        self.HANDLERS = {
            'select': self.method_select,
            'set_action': self.method_set_action,
            'subscribe': self.method_subscribe,
        }

        self.SELECT_HANDLERS = {
            'my_info': self.select_my_info,
            'item_info': self.select_item_info,
            'players': self.select_players,
            'items': self.select_items,
            'nearest_enemy': self.select_nearest_enemy,
            'enemy_items_in_my_firing_range': self.select_enemy_items_in_my_firing_range
        }

    def get_percentage_hit_points(self):
        return max(0, round(100 * self.hit_points / self.start_hit_points))

    def get_action_status(self):
        return self._state["action"]

    def set_state_idle(self):
        self._fight_handler.send_im_idle(self.id)
        self._state = {'action': 'idle'}

    def set_state_dead(self):
        if self.size:
            self._fight_handler.clear_from_map(self)
        self._state = {'action': 'dead'}

    def set_coordinates(self, coordinates):
        self.coordinates = coordinates
        self._fight_handler.send_range_events(self.id)

    @property
    def is_executable(self):
        if self.role == ROLE.UNIT:
            if self.coordinates is not None:
                return True
        elif self.code is not None:
            return True
        return False

    @gen.coroutine
    def start(self):
        if not self.is_executable:
            return
        self._env = yield self._fight_handler.get_environment(self.player[PLAYER.ENV_NAME])
        result = yield self._env.run_code(self.code)
        while True:
            if result is not None:
                status = result.pop('status')
                if status and status != STATUS.SUCCESS:
                    pass  # TODO:
                yield self.handle_result(result)
            result = yield self._env.read_message()

    @gen.coroutine
    def handle_result(self, data):
        handler_name = data.pop('method', None)
        if handler_name is None:
            # raise Exception("WTF")
            return  # TODO: this data is not from commander, then for what?
        handler = self.HANDLERS[handler_name]
        handler(**data)

    @gen.coroutine
    def method_select(self, fields):
        data = []
        for field in fields:
            field_key = field.get('field')
            if field_key is None:
                data.append({'error': 'wrong format, field did not passed'})
                continue
            if field_key not in self.SELECT_HANDLERS:
                data.append({'error': 'wrong format, wrong field'})
                continue

            data.append(self.SELECT_HANDLERS[field_key](field.get('data')))

        yield self._env.select_result(data)

    def select_my_info(self, data):
        return self.select_item_info({ATTRIBUTE.ID: self.id})

    def select_item_info(self, data):
        return self._fight_handler.get_item_info(data[ATTRIBUTE.ID])

    def select_players(self, data):
        return self._fight_handler.get_public_players_info(data, self.player[ATTRIBUTE.ID])

    def select_items(self, data):
        return self._fight_handler.get_group_item_info(data, self.player[ATTRIBUTE.ID])

    def select_nearest_enemy(self, data):
        return self._fight_handler.get_nearest_enemy(data[ATTRIBUTE.ID])

    def select_enemy_items_in_my_firing_range(self, data):
        return self._fight_handler.get_enemy_items_in_my_firing_range(data[ATTRIBUTE.ID])

    @gen.coroutine
    def method_set_action(self, action, data):
        try:
            self.action = self._actions_handlers.parse_action_data(action, data)
        except ActionValidateError as e:
            yield self._env.bad_action(e)
        else:
            yield self._env.confirm()

    @gen.coroutine
    def method_subscribe(self, event, lookup_key, data):
        result = self._fight_handler.subscribe(event, self.id, lookup_key, data)
        if not result:
            yield self._env.bad_action()
            return
        yield self._env.confirm()

    def do_frame_action(self):
        try:
            self._state = self._actions_handlers.do_action(self.action)
        except ActionValidateError:
            self.set_state_idle()

    @gen.coroutine
    def send_event(self, lookup_key, data):
        yield self._env.send_event(lookup_key, data)


class CraftItem(Item):
    def __init__(self, item_data, player, fight_handler):
        self.id = self.generate_id()
        self.coordinates = item_data.get(ATTRIBUTE.COORDINATES)
        self.tile_position = item_data.get(ATTRIBUTE.COORDINATES)[:]
        self.level = item_data.get(ATTRIBUTE.LEVEL)
        self.alias = item_data.get(ATTRIBUTE.ALIAS)
        self.item_type = item_data.get(ATTRIBUTE.ITEM_TYPE)
        self.player = player
        self.role = ROLE.CRAFT

    @property
    def info(self):
        return {
            ATTRIBUTE.ID: self.id,
            ATTRIBUTE.PLAYER_ID: self.player.get("id"),
            ATTRIBUTE.ROLE: self.role,
            ATTRIBUTE.COORDINATES: self.coordinates,
            ATTRIBUTE.LEVEL: self.level
        }

