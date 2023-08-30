"""
Support for Personal Capital sensors.

For more details about this platform, please refer to the documentation at
https://github.com/chotaling1/sensor.personalcapital
"""

import logging
import voluptuous as vol
import json
import time
from datetime import timedelta, date, datetime
from homeassistant.helpers.entity import Entity
import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import (PLATFORM_SCHEMA)
from homeassistant.util import Throttle
import pandas
import pickle
import requests
import re

__version__ = '0.1.1'

CONF_EMAIL = 'email'
CONF_PASSWORD = 'password'
CONF_UNIT_OF_MEASUREMENT = 'unit_of_measurement'
CONF_CATEGORIES = 'monitored_categories'

SESSION_FILE = '.pc-session'
DATA_PERSONAL_CAPITAL = 'personalcapital_cache'

ATTR_NETWORTH = 'networth'
ATTR_ASSETS = 'assets'
ATTR_LIABILITIES = 'liabilities'
ATTR_INVESTMENT = 'investment'
ATTR_MORTGAGE = 'mortgage'
ATTR_CASH = 'cash'
ATTR_OTHER_ASSET = 'other_asset'
ATTR_OTHER_LIABILITY = 'other_liability'
ATTR_CREDIT = 'credit'
ATTR_LOAN = 'loan'
ATTR_BUDGET_SPENDING = "budget_spending"

SCAN_INTERVAL = timedelta(minutes=5)
MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=30)

SENSOR_TYPES = {
    ATTR_INVESTMENT: ['INVESTMENT', '', 'investmentAccountsTotal', 'Investment', False],
    ATTR_MORTGAGE: ['MORTGAGE', '', 'mortgageAccountsTotal', 'Mortgage', True],
    ATTR_CASH: ['BANK', 'Cash', 'cashAccountsTotal', 'Cash', False],
    ATTR_OTHER_ASSET: ['OTHER_ASSETS', '', 'otherAssetAccountsTotal', 'Other Asset', False],
    ATTR_OTHER_LIABILITY: ['OTHER_LIABILITIES', '', 'otherLiabilitiesAccountsTotal', 'Other Liability', True],
    ATTR_CREDIT: ['CREDIT_CARD', '', 'creditCardAccountsTotal', 'Credit', True],
    ATTR_LOAN: ['LOAN', '', 'loanAccountsTotal', 'Loan', True],
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_EMAIL): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
    vol.Optional(CONF_UNIT_OF_MEASUREMENT, default='USD'): cv.string,
    vol.Optional(CONF_CATEGORIES, default=[]): vol.All(cv.ensure_list, [vol.In(SENSOR_TYPES)]),
})

_CONFIGURING = {}
_LOGGER = logging.getLogger(__name__)


def request_app_setup(hass, config, pc, add_devices, discovery_info=None):
    """Request configuration steps from the user."""
    configurator = hass.components.configurator

    def personalcapital_configuration_callback(data):
        """Run when the configuration callback is called."""
        pc.two_factor_authenticate(TwoFactorVerificationModeEnum.SMS, data.get('verification_code'))
        result = pc.authenticate_password(config.get(CONF_PASSWORD))

        if result == RequireTwoFactorException:
            configurator.notify_errors(_CONFIGURING['personalcapital'], "Invalid verification code")
        else:
            save_session(hass, pc.get_session())
            continue_setup_platform(hass, config, pc, add_devices, discovery_info)

    if 'personalcapital' not in _CONFIGURING:
        try:
            pc.login(config.get(CONF_EMAIL), config.get(CONF_PASSWORD))
        except RequireTwoFactorException:
            pc.two_factor_challenge(TwoFactorVerificationModeEnum.SMS)

    _CONFIGURING['personalcapital'] = configurator.request_config(
        'Personal Capital',
        personalcapital_configuration_callback,
        description="Verification code sent to phone",
        submit_caption='Verify',
        fields=[{
            'id': 'verification_code',
            'name': "Verification code",
            'type': 'string'}]
    )


def load_session(hass):
    try:
        with open(hass.config.path(SESSION_FILE)) as data_file:
            cookies = {}
            try:
                cookies = json.load(data_file)
            except ValueError as err:
                return {}
            return cookies
    except IOError as err:
        return {}


def save_session(hass, session):
    with open(hass.config.path(SESSION_FILE), 'w') as data_file:
        data_file.write(json.dumps(session))


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the Personal Capital component."""
    pc = PersonalCapital()
    session = load_session(hass)

    if len(session) > 0:
        pc.set_session(session)

        try:
            pc.login(config.get(CONF_EMAIL), config.get(CONF_PASSWORD))
            continue_setup_platform(hass, config, pc, add_devices, discovery_info)
        except RequireTwoFactorException:
            request_app_setup(hass, config, pc, add_devices, discovery_info)
    else:
        request_app_setup(hass, config, pc, add_devices, discovery_info)


def continue_setup_platform(hass, config, pc, add_devices, discovery_info=None):
    """Set up the Personal Capital component."""
    if "personalcapital" in _CONFIGURING:
        hass.components.configurator.request_done(_CONFIGURING.pop("personalcapital"))

    rest_pc = PersonalCapitalAccountData(pc, config)
    uom = config[CONF_UNIT_OF_MEASUREMENT]
    sensors = []
    categories = config[CONF_CATEGORIES] if len(config[CONF_CATEGORIES]) > 0 else SENSOR_TYPES.keys()
    sensors.append(PersonalCapitalNetWorthSensor(rest_pc, config[CONF_UNIT_OF_MEASUREMENT]))
    sensors.append(PersonalCapitalBudgetSensor(rest_pc, hass, uom))
    for category in categories:
        sensors.append(PersonalCapitalCategorySensor(hass, rest_pc, uom, category))
    add_devices(sensors, True)


class PersonalCapitalNetWorthSensor(Entity):
    """Representation of a personalcapital.com net worth sensor."""

    def __init__(self, rest, unit_of_measurement):
        """Initialize the sensor."""
        self._rest = rest
        self._unit_of_measurement = unit_of_measurement
        self._state = None
        self._assets = None
        self._liabilities = None
        self.update()

    def update(self):
        """Get the latest state of the sensor."""
        self._rest.update()
        data = self._rest.data.json()['spData']
        self._state = data.get('networth', 0.0)
        self._assets = data.get('assets', 0.0)
        self._liabilities = format_balance(True, data.get('liabilities', 0.0))

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'PC Networth'

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measure this sensor expresses itself in."""
        return self._unit_of_measurement

    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        return 'mdi:coin'

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the sensor."""
        attributes = {
            ATTR_ASSETS: self._assets,
            ATTR_LIABILITIES: self._liabilities
        }
        return attributes

class PersonalCapitalBudgetSensor(Entity):
    """Representation a monthly spending from personalcapital.com sensor."""

    def __init__(self, rest, hass, unit_of_measurement):
        self.hass = hass
        self._rest = rest
        self._unit_of_measurement = unit_of_measurement
        self._state = None

    def update(self):
        """Get the latest state of the sensor."""
        self.hass.data["budget"] = {'spendCategories':[]}
        transactionCategories = self._rest.transactions
        for i in transactionCategories.index:
            print('Amount spent in ' + transactionCategories['name'][i] + ':', transactionCategories['amount'][i], "\n\n")
            self.hass.data['budget'].get('spendCategories').append(
                {
                    'name': transactionCategories['name'][i],
                    'amount': transactionCategories['amount'][i]
                }
            )
        
        self._state = format_balance(False, transactionCategories['amount'].sum())

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'PC Budget'

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measure this sensor expresses itself in."""
        return self._unit_of_measurement

    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        return 'mdi:coin'

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the sensor."""
        attributes = {
            ATTR_BUDGET_SPENDING: self.hass.data['budget']
        }
        
        return attributes

class PersonalCapitalCategorySensor(Entity):
    """Representation of a personalcapital.com sensor."""

    def __init__(self, hass, rest, unit_of_measurement, sensor_type):
        """Initialize the sensor."""
        self.hass = hass
        self._rest = rest
        self._productType = SENSOR_TYPES[sensor_type][0]
        self._accountType = SENSOR_TYPES[sensor_type][1]
        self._balanceName = SENSOR_TYPES[sensor_type][2]
        self._name = f'PC {SENSOR_TYPES[sensor_type][3]}'
        self._inverse_sign = SENSOR_TYPES[sensor_type][4]
        self._state = None
        self._unit_of_measurement = unit_of_measurement

    def update(self):
        """Get the latest state of the sensor."""
        self._rest.update()
        data = self._rest.data.json()['spData']
        self._state = format_balance(self._inverse_sign, data.get(self._balanceName, 0.0))
        accounts = data.get('accounts')
        self.hass.data[self._productType] = {'accounts': []}

        for account in accounts:
            if ((self._productType == account.get('productType')) or (self._accountType == account.get('accountType', ''))) and account.get('closeDate', '') == '':
                self.hass.data[self._productType].get('accounts').append({
                    "name": account.get('name', ''),
                    "firm_name": account.get('firmName', ''),
                    "logo": account.get('logoPath', ''),
                    "balance": format_balance(self._inverse_sign, account.get('balance', 0.0)),
                    "account_type": account.get('accountType', ''),
                    "url": account.get('homeUrl', ''),
                    "currency": account.get('currency', ''),
                    "refreshed": how_long_ago(account.get('lastRefreshed', 0)) + ' ago',
                })

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement this sensor expresses itself in."""
        return self._unit_of_measurement

    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        return 'mdi:coin'

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the sensor."""
        return self.hass.data[self._productType]


class PersonalCapitalAccountData(object):
    """Get data from personalcapital.com"""

    def __init__(self, pc, config):
        self._pc = pc
        self.data = None
        self.transactions = None
        self._config = config

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        """Get latest data from personal capital"""
        self.data = self._pc.fetch('/newaccount/getAccounts')

        if not self.data or not self.data.json()['spHeader']['success']:
            self._pc.login(self._config[CONF_EMAIL], self._config[CONF_PASSWORD])
            self.data = self._pc.fetch('/newaccount/getAccounts')

            current_date = date.now()
            request_body = {
                'startDate':str(current_date.year) + '-' + str(current_date.month) + '1',
                'endDate':str(current_date),
            }

        if not self.transactions:
            self.getTransactions()

    def getTransactions(self):
        now = datetime.now()
        date_format = '%Y-%m-%d'
        start_date = str(now.year) + "-" + str(now.month) + "-1"
        end_date = now.strftime(date_format)
        transactions_response = self._pc.fetch('/transaction/getUserTransactions', {
            'sort_cols': 'transactionTime',
            'sort_rev': 'true',
            'startDate': start_date,
            'endDate': end_date,
            'component': 'DATAGRID'
        })

        categories = self._pc.fetch('/transactioncategory/getCategories').json()['spData']
        transactionsData = transactions_response.json()['spData']
        transactions = transactionsData['transactions']

        splitTransactions = []
        for i in transactions:
            if ('splits' in i.keys()):
                transactions.remove(i)
                for split in i['splits']:
                    splitTransactions.append(split)

            
        df = pandas.DataFrame(transactions)
        df_filtered = df.loc[df['includeInCashManager'] == True]
        for category in categories:
            df_filtered['categoryName'].mask(df_filtered['categoryId'] == category['transactionCategoryId'], category['name'], inplace = True)
        
        df_filtered['amount'].mask(
            (df_filtered['isCashIn'] == True) |
            (df_filtered['isInterest'] == True) |
            (df_filtered['isIncome'] == True) |
            (df_filtered['isCredit'] == True), df['amount'] * -1, inplace=True)

        grouped_df = df_filtered.groupby('categoryName')
        sum = []
        for key, item in grouped_df:
            result = { 'name': key, 'amount': item['amount'].sum(), 'categoryId': item.categoryId.iat[0]}
            sum.append(result)

        amount_df = pandas.DataFrame(sum, columns=['name', 'amount', 'categoryId'])

        for split in splitTransactions:
            amount_df['amount'].mask(amount_df['categoryId'] == split['categoryId'], amount_df['amount'] + split['amount'], inplace = True)

        sorted_df = amount_df.sort_values(by=['amount'], ascending = False)
        self.transactions = sorted_df



def how_long_ago(last_epoch):
    a = last_epoch
    b = time.time()
    c = b - a
    days = c // 86400
    hours = c // 3600 % 24
    minutes = c // 60 % 60

    if days > 0:
        return str(round(days)) + ' days'
    if hours > 0:
        return str(round(hours)) + ' hours'
    return str(round(minutes)) + ' minutes'


def format_balance(inverse_sign, balance):
    return -1.0 * balance if inverse_sign is True else balance



csrf_regexp = re.compile(r"window.csrf ='([a-f0-9-]+)'")
user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36'
base_url = 'https://home.personalcapital.com'
ident_endpoint = base_url + '/page/login/goHome'
api_endpoint = base_url + '/api'

SP_HEADER_KEY = "spHeader"
SUCCESS_KEY = "success"
CSRF_KEY = "csrf"
AUTH_LEVEL_KEY = "authLevel"
ERRORS_KEY = "errors"

def getSpHeaderValue(result, valueKey):
    if (SP_HEADER_KEY in result) and (valueKey in result[SP_HEADER_KEY]):
        return result[SP_HEADER_KEY][valueKey]
    return None

def getErrorValue(result):
    try:
        return getSpHeaderValue(result, ERRORS_KEY)[0]['message']
    except (ValueError, IndexError):
        return None

class AuthLevelEnum(object):
    USER_REMEMBERED = "USER_REMEMBERED"

class TwoFactorVerificationModeEnum(object):
    SMS = 0
    # PHONE = 1
    EMAIL = 2

class RequireTwoFactorException(Exception):
    pass

class LoginFailedException(Exception):
    pass

class PersonalCapital(object):
    def __init__(self):
        self.__session = requests.Session()
        self.__session.headers.update({'user-agent': user_agent})
        self.__csrf = ""

    def login(self, username, password):
        initial_csrf = self.__get_csrf_from_home_page(ident_endpoint)
        if initial_csrf is None:
          LoginFailedException("Unable to extract initial CSRF token")
        csrf, auth_level = self.__identify_user(username, initial_csrf)

        if csrf is None or auth_level is None:
          LoginFailedException("Unable to extract CSRF token and user auth level")
        if csrf and auth_level:
            self.__csrf = csrf
            if auth_level != AuthLevelEnum.USER_REMEMBERED:
                raise RequireTwoFactorException()
            result = self.__authenticate_password(password).json()
            if getSpHeaderValue(result, SUCCESS_KEY) == False:
                raise LoginFailedException(getErrorValue(result))
        else:
            raise LoginFailedException()

    def authenticate_password(self, password):
        return self.__authenticate_password(password)

    def two_factor_authenticate(self, mode, code):
        if mode == TwoFactorVerificationModeEnum.SMS:
            return self.__authenticate_sms(code)
        elif mode == TwoFactorVerificationModeEnum.EMAIL:
            return self.__authenticate_email(code)

    def two_factor_challenge(self, mode):
        if mode == TwoFactorVerificationModeEnum.SMS:
            return self.__challenge_sms()
        elif mode == TwoFactorVerificationModeEnum.EMAIL:
            return self.__challenge_email()

    def fetch(self, endpoint, data = None):
        """
        for getting data after logged in
        """
        payload = {
            "lastServerChangeId": "-1",
            "csrf": self.__csrf,
            "apiClient": "WEB"
        }
        if data is not None:
            payload.update(data)

        return self.post(endpoint, payload)

    def post(self, endpoint, data):
        response = self.__session.post(api_endpoint + endpoint, data)
        return response

    def get_session(self):
        """
        return cookies as a dictionary
        """
        return requests.utils.dict_from_cookiejar(self.__session.cookies)

    def set_session(self, cookies):
        """
        sets the cookies (should be a dictionary)
        """
        self.__session.cookies = requests.utils.cookiejar_from_dict(cookies)

    # private methods

    def save_session(self, filename):
      session_data = {
          "csrf": self.__csrf,
          "cookies": self.__session.cookies._cookies, 
      }
      with open(filename, 'wb') as fh:
        pickle.dump(session_data, fh) 

    def load_session(self, filename):
      with open(filename, 'rb') as fh:
        data = pickle.load(fh) 
        jar = requests.cookies.RequestsCookieJar() 
        jar._cookies = data["cookies"]
        self.__session.cookies = jar
        self.__csrf = data["csrf"]


    def __get_csrf_from_home_page(self, url):
        r = self.__session.get(url)
        found_csrf = csrf_regexp.search(r.text)

        if found_csrf:
            return found_csrf.group(1)
        return None

    def __identify_user(self, username, csrf):
        """
        Returns reusable CSRF code and the auth level as a 2-tuple
        """
        data = {
            "username": username,
            "csrf": csrf,
            "apiClient": "WEB",
            "bindDevice": "false",
            "skipLinkAccount": "false",
            "redirectTo": "",
            "skipFirstUse": "",
            "referrerId": "",
        }

        r = self.post("/login/identifyUser", data)

        if r.status_code == requests.codes.ok:
            result = r.json()
            new_csrf = getSpHeaderValue(result, CSRF_KEY)
            auth_level = getSpHeaderValue(result, AUTH_LEVEL_KEY)
            return (new_csrf, auth_level)

        return (None, None)

    def __generate_challenge_payload(self, challenge_type):
        return {
            "challengeReason": "DEVICE_AUTH",
            "challengeMethod": "OP",
            "challengeType": challenge_type,
            "apiClient": "WEB",
            "bindDevice": "false",
            "csrf": self.__csrf
        }

    def __generate_authentication_payload(self, code):
        return {
            "challengeReason": "DEVICE_AUTH",
            "challengeMethod": "OP",
            "apiClient": "WEB",
            "bindDevice": "false",
            "code": code,
            "csrf": self.__csrf
        }

    def __challenge_email(self):
        data = self.__generate_challenge_payload("challengeEmail")
        return self.post("/credential/challengeEmail", data)

    def __authenticate_email(self, code):
        data = self.__generate_authentication_payload(code)
        return self.post("/credential/authenticateEmailByCode", data)

    def __challenge_sms(self):
        data = self.__generate_challenge_payload("challengeSMS")
        return self.post("/credential/challengeSms", data)

    def __authenticate_sms(self, code):
        data = self.__generate_authentication_payload(code)
        return self.post("/credential/authenticateSms", data)

    def __authenticate_password(self, passwd):
        data = {
            "bindDevice": "true",
            "deviceName": "Personal Capital Python API",
            "redirectTo": "",
            "skipFirstUse": "",
            "skipLinkAccount": "false",
            "referrerId": "",
            "passwd": passwd,
            "apiClient": "WEB",
            "csrf": self.__csrf
        }
        return self.post("/credential/authenticatePassword", data)
