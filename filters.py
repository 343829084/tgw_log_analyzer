#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pandas as pd

def thousands_sep(num, digits=None):
    """为数字加上千位符，可选保留小数位数

    如果指定小数位数，则不足者补0，超出的四舍五入到指定小数位数。

    参数:
        num: 要格式化的数值
        digits: 要保留的小数位数。缺省为使用数字原有的小数位数
    """
    if digits is None:
        return '{:,}'.format(num)
    else:
        return '{:,.{:}f}'.format(num, digits)

def as_time(dt, default='--'):
    if dt:
        return str(dt.time())
    else:
        return default

def as_datetime(dt, default='--'):
    if dt:
        return str(dt)
    else:
        return default

def timedelta(dt, unit='1s'):
    return dt / pd.Timedelta(unit)

def conn_status(status):
    if status == 'connected':
        return u'连接后未断开'
    elif status == 'failed':
        return u'连接失败'
    elif status == 'closed':
        return u'连接后断开'
    elif status == 'logout':
        return u'登录失败'
    else:
        return status
