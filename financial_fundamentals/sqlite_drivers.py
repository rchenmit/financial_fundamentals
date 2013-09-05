'''
Created on Aug 21, 2013

@author: akittredge
'''

import numpy as np
import dateutil.parser
import random
from financial_fundamentals.indicies import S_P_500_TICKERS
from zipline.utils.tradingcalendar import get_trading_days

class SQLiteTimeseries(object):
    def __init__(self, connection, table, metric):
        connection.row_factory = sqlite3.Row
        self._connection = connection
        self._table = table
        self._metric = metric
        self._ensure_table_exists(connection, table)
        
    @classmethod
    def _ensure_table_exists(cls, connection, table):
        cursor = connection.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row['name'] for row in cursor.fetchall()]
        if table not in tables:
            cls.create_table(connection, table)
        
    get_query = '''SELECT value, symbol, metric, date from {} 
                    WHERE symbol = ?
                    AND date in ({})
                    AND metric =  ?
                '''
    def get(self, symbol, dates):
        '''return metric values for symbols and dates.'''
        with self._connection:
            qry = self.get_query.format(self._table, 
                                        ','.join('?' * len(dates)),
                                        )
            cursor = self._connection.cursor()
            args = [symbol] + dates + [self._metric]
            cursor.execute(qry, args)
            for row in cursor.fetchall():
                yield self._beautify_record(record=row)
       
    insert_query = 'INSERT INTO {} (symbol, date, metric, value) VALUES (?, ?, ?, ?)'
    def set(self, symbol, records):
        '''records is a sequence of date, value items.'''
        with self._connection:
            for date, value in records:
                args = (symbol, date, self._metric, value)
                self._connection.execute(self.insert_query.format(self._table), args)
        
    create_stm = 'CREATE TABLE {:s} (date timestamp, symbol text, metric text, value real)'
    @classmethod
    def create_table(cls, connection, table):
        with connection:
            connection.execute(cls.create_stm.format(table))
            
    @staticmethod
    def _beautify_record(record):
        '''Cast metric to np.float and make date tz-aware.
        
        '''
        return (dateutil.parser.parse(record['date']).replace(tzinfo=pytz.UTC), 
                    np.float(record['value']))
        
class SQLiteIntervalseries(object):
    def get(self, symbol, date):
        '''return the metric value of symbol on date.'''
        
    def set_interval(self, symbol, start, end, value):
        '''set value for interval start and end.'''
        
import unittest
import datetime
import pytz
import sqlite3
from collections import defaultdict
class SQLiteTimeseriesTestCase(unittest.TestCase):
    table = 'price'
    metric = 'Adj Close'
    def setUp(self):
        self.connection = sqlite3.connect(':memory:')
        self.driver = SQLiteTimeseries(connection=self.connection, 
                                       table=self.table, 
                                       metric=self.metric)

    def test_single_get(self):
        symbol = 'ABC'
        date = datetime.datetime(2012, 12, 1, tzinfo=pytz.UTC)
        price = 6.5
        self.connection.execute('INSERT INTO {} (symbol, date, metric, value) VALUES (?, ?, ?, ?)'\
                                .format(self.table), (symbol, date, self.metric, price))
        cache_date, cache_price = self.driver.get(symbol=symbol, dates=[date]).next()
        self.assertEqual(cache_price, price)
        self.assertEqual(cache_date, date)
        
    def insert_date_combos(self, symbol_date_combos):
        test_vals = defaultdict(dict)
        for symbol, date in symbol_date_combos:
            price = random.randint(0, 1000)
            self.connection.execute('INSERT INTO {} (symbol, date, metric, value) VALUES (?, ?, ?, ?)'\
                                    .format(self.table), (symbol, date, self.metric, price))
            test_vals[symbol][date] = price
        return test_vals
        
    def test_multiple_get(self):
        symbols = ['ABC', 'XYZ']
        dates = [datetime.datetime(2012, 12, 1, tzinfo=pytz.UTC),
                 datetime.datetime(2012, 12, 2, tzinfo=pytz.UTC),
                 datetime.datetime(2012, 12, 15, tzinfo=pytz.UTC),
                 ]
        symbol_date_combos = [(symbol, date) for symbol in symbols for date in dates]
        price_dict = self.insert_date_combos(symbol_date_combos)
        
        for symbol in symbols:
            cached_values = list(self.driver.get(symbol=symbol, dates=dates))
            cache_dict = {date : price for date, price in cached_values}
            self.assertDictEqual(price_dict[symbol], cache_dict)
        
    def test_date_query(self):
        '''assert we only get the dates we want.'''
        symbols = ['ABC', 'XYZ']
        dates = [datetime.datetime(2012, 12, 1, tzinfo=pytz.UTC),
                 datetime.datetime(2012, 12, 2, tzinfo=pytz.UTC),
                 datetime.datetime(2012, 12, 3, tzinfo=pytz.UTC),
                 ]
        symbol_date_combos = [(symbol, date) for symbol in symbols for date in dates]
        prices = self.insert_date_combos(symbol_date_combos)
        self.insert_date_combos([('ABC', datetime.datetime(2012, 12, 15))])
        for symbol in symbols:
            cached_values = self.driver.get(symbol=symbol, dates=dates)
            cache_dict = {date : price for date, price in cached_values}
            self.assertDictEqual(prices[symbol], cache_dict)
        
    def test_volume(self):
        '''make sure a larger number of records doesn't choke it somehow.'''
        symbols = S_P_500_TICKERS[:200]
        datetimeindex = get_trading_days(start=datetime.datetime(2012, 1, 1, tzinfo=pytz.UTC), 
                                 end=datetime.datetime(2012, 7, 4, tzinfo=pytz.UTC))
        dates = [datetime.datetime(d.date().year, d.date().month, d.date().day).replace(tzinfo=pytz.UTC) 
                 for d in datetimeindex]
        symbol_date_combos = [(symbol, date) for symbol in symbols for date in dates]
        test_vals = self.insert_date_combos(symbol_date_combos)
        for symbol in symbols:
            cached_values = self.driver.get(symbol=symbol, dates=dates)
            cache_dict = {date : price for date, price in cached_values}    
            self.assertDictEqual(test_vals[symbol], cache_dict)
        
    def test_set(self):
        symbol = 'ABC'
        date = datetime.datetime(2012, 12, 1, tzinfo=pytz.UTC)
        price = 6.5
        self.driver.set(symbol=symbol, records=[(date, price)])
        qry = 'SELECT * FROM {}'.format(self.table)
        row = self.connection.execute(qry).fetchone()
        self.assertEqual(row['symbol'], symbol)
        self.assertEqual(row['metric'], self.metric)
        self.assertEqual(row['value'], price)

        