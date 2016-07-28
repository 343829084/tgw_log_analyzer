#!/usr/bin/env python
# -*- coding: utf-8 -*-

def thousands_sep(num):
    """把数字转换为带千位分隔符的字符串

    Args:
        num: 要转换的数字。如果是小数，则只为整数部分加上千位分隔符

    Returns:
        字符串，转换结果
    """
    parts = str(num).split('.')
    s = parts[0][::-1] # 反转
    parts[0] = ",".join([s[i:i+3] for i in range(0,len(s),3)])   # 每三个数字加一个逗号
    parts[0] = parts[0][::-1] # 再反转为正常顺序

    return ".".join(parts)

def precision(digits=2):
    def filter(s):
        parts = str(s).split('.')
        integer = parts[0]
        decimal = parts[1] if len(parts) > 1 else ''

        if digits > 0:
            return ".".join((integer, (decimal + '000')[:digits]))
        else:
            return integer

    return filter

