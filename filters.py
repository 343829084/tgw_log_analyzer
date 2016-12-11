#!/usr/bin/env python
# -*- coding: utf-8 -*-

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

