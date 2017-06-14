import datetime
import logging
from zipfile import ZipFile
from StringIO import StringIO

import requests
import pandas as pd

FLOW_URL = 'https://flow.polar.com'
FLOW_LOGIN_URL = "{}/ajaxLogin".format(FLOW_URL)
FLOW_LOGIN_POST_URL = "{}/login".format(FLOW_URL)
ACTIVITIES_URL = "{}/training/getCalendarEvents".format(FLOW_URL)

logger = logging.getLogger(__name__)


# TODO: look into this url for gathering training data:
#    https://flow.polar.com/training/analysis/<id>/range/data
#    https://flow.polar.com/training/analysis/71760805/range/data
# TODO: look into this url for gathering activity data:
#    https://flow.polar.com/activity/data/<end>/<start>
#    eg: https://flow.polar.com/activity/data/30.3.2015/10.5.2015

class FlowClient(object):

    """Interact with the (unofficial) Polar Flow API."""

    def __init__(self):
        self.session = requests.session()

    def login(self, username, password):
        postdata = {'email': username,
                    'password': password,
                    'returnURL': '/'}
        # We need to go here to gather some cookies
        self.session.get(FLOW_LOGIN_URL)
        resp = self.session.post(FLOW_LOGIN_POST_URL, data=postdata)
        if resp.status_code != 200:
            resp.raise_for_status()

    # FIXME: these aren't really activities as Flow defines them, they're
    # training sessions?
    # activity is the activity tracking stuff
    def activities(self, *args, **kwargs):
        """Return all activities between ``start_date`` and ``end_date``.

        ``end_date`` defaults to the current time, ``start_date`` defaults to
        30  days before ``end_date``.
        """
        return list(self.iter_activities(*args, **kwargs))

    def iter_activities(self, start_date=None, end_date=None):
        """Return a generator yielding `Activity` objects."""
        logger.debug("Fetching activities between %s and %s",
                     start_date, end_date)
        end_date = end_date or datetime.datetime.now()
        start_date = start_date or (end_date - datetime.timedelta(days=30))
        params = {'start': _format_date(start_date),
                  'end': _format_date(end_date)}
        resp = self.session.get(ACTIVITIES_URL, params=params)
        resp.raise_for_status()
        for data in resp.json():
            yield Activity(self.session, data)


# FIXME: it would be ideal if Activity didn't have to take a session object
# and instead just took an id (or optionally the activity data if already
# available)
class Activity(object):

    """Represents a single activity in Polar Flow.

    ``session`` must be an already authenticated `Session` object.

    """

    def __init__(self, session, data):
        self.session = session
        self.data = data

    def __repr__(self):
        return "{}({})".format(type(self).__name__, self.data['listItemId'])

    def __getattr__(self, name):
        try:
            return self.data[name]
        except KeyError:
            raise AttributeError(name)

    def __dir__(self):
        return sorted(set(self.data.keys() +
                          dir(type(self)) +
                          list(self.__dict__)))

    def _make_dataframe(self, content):
        """
        convert the csv response to a pandas dataframe
        
        returns
        -------
        df:     pandas dataframe of numeric data present in csv
        header: dictionary of user details provided at the top of the csv
        """
        rows = content.split('\n')
        header = {k: v for k, v in zip(rows[0].split(','), rows[1].split(','))}
        columns = rows[2].split(',')
        data = map(lambda x: x.split(','), rows[3:-1]) #last row is funky
        return (pd.DataFrame(columns=columns, data=data), header)

    def _grab_data(self, format, to_dataframe=False):
        """grab tcx of csv data depending on what the user wants"""
        logging.debug("Fetching " + format + " file for" + self.data['url'])
        # tcx_url = FLOW_URL + self.data['url'] + '/export/tcx'
        url = FLOW_URL + '/api/export/training/' + format + '/' + str(self.listItemId)

        resp = self.session.get(url)
        resp.raise_for_status()
        if to_dataframe:
            return self._make_dataframe(resp.content)
        return resp.content

    def tcx(self):
        """Return the contents of the TCX file for the given activity.

        ``activity`` can either be an id or an activity dictionary
        (as returned by `get_activities`).

        """
        return self._grab_data('tcx')

    def csv(self):
        """Return the contents of the CSV file for the given activity.

        ``activity`` can either be an id or an activity dictionary
        (as returned by `get_activities`).

        """
        return self._grab_data('csv')

    def dataframe(self):
        return self._grab_data('csv', to_dataframe=True)


def _format_date(dt):
    return dt.strftime('%d.%m.%Y')
