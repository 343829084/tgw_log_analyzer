#!/usr/bin/env python2
# vim: set fileencoding=utf-8 tabstop=4 expandtab shiftwidth=4 softtabstop=4:

# Imports
import argparse
import bisect
import codecs
from collections import defaultdict
import exceptions
import locale
import logging

import numpy as np
import pandas as pd
import re
import os
import sys
import inspect
import jinja2
from distutils.dir_util import mkpath

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from mpl_toolkits.axes_grid1 import make_axes_locatable

import filters
import chart_util

VERSION=u"20161212"

matplotlib.style.use('ggplot')

# 存放结果的目录
DEFAULT_OUTPUT_DIR = 'result'
DEFAULT_LOG_ENCODING = 'utf-8,gbk'

# HTML报告模板目录
HTML_TEMPLATE_DIR = '.'
HTML_TEMPLATE_FILENAME = 'html_template.html'
HTML_REPORT_FILENAME = 'index.html'

# TEXT报告模板目录
TEXT_TEMPLATE_DIR = '.'
TEXT_TEMPLATE_FILENAME = 'text_template.html'

def summary(array):
    """返回array的基本统计信息.

    :array: 输入的numpy.array
    :returns: dict

    """
    return {
        'count' : len(array),
        'std'   : array.std(),
        'max'   : array.max(),
        'min'   : array.min(),
        'mean'  : array.mean(),
        'p90'   : np.percentile(array, 90),
    }


class DateTime(object):

    """日期、时间解释器"""
    re_datetime = re.compile(r'(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2}) (?P<hour>\d\d):(?P<minute>\d\d):(?P<second>\d\d).(?P<microsecond>\d{6})')

    @classmethod
    def from_string(cls, s):
        """解释YYYY-MM-DD HH:MM:SS.dddddd的字符串

        :s: 日期、时间字符串
        :returns: 以微秒为单位的数值。解释失败抛出异常

        """
        m = cls.re_datetime.match(s)
        if not m:
            raise exceptions.ValueError(u'"{0}" is invalid date time'.format(s))

        return ((long(m.group('hour')) * 60 + long(m.group('minute'))) * 60 + long(m.group('second'))) * 1000000 + long(m.group('microsecond'))

    @classmethod
    def to_string(cls, t):
        return '{0:02}:{1:02}:{2:02}.{3:03}'.format(
            t / 10000000, t / 100000 % 100, t / 100 % 100, t % 1000)


class Result(object):
    def __init__(self, summary, details):
        """初始化.

        details['datetime']就是对应的时间。

        参数:
            summary: 汇总dict
            details: DataFrame，详细数据
        """

        self.summary = summary
        self.details = pd.DataFrame(details)

        if 'datetime' in details:
            self.details = self.details.sort_values('datetime')

    def summary(self):
        return self.summary

    def first(self):
        return self.details.iloc[0]

    def last(self):
        return self.details.iloc[len(self.details)]

    def find_le(self, datetime):
        i = self.details['datetime'].searchsorted(datetime, side='right')
        if i:
            return self.details.iloc[i-1]

        raise exceptions.ValueError

    def find_ge(self, datetime):
        i = self.details['datetime'].searchsorted(datetime, side='left')
        if i != len(self.details):
            return self.details.iloc[i]

        raise exceptions.ValueError


class ParserBase(object):
    """分析器的基类，定义几个接口方法"""
    def __init__(self, parser_name):
        """初始化

        :parser_name: 分析器的名称
        """
        #: 分析器的名称，用于按名称取分析结果
        self.parser_name = parser_name

    def parse(self, line_time, line_content):
        """处理一行

        :line_time: 行的时间
        :line_content: 时间之后的内容
        :returns: 是否匹配了这行
        """
        raise exceptions.NotImplemented

    def finish(self):
        """结果对文件的处理。

        可用于分析前面收集到的信息。

        :returns: 分析结果，一般是dict
        """
        raise exceptions.NotImplemented

    def on_startup(self, **kwargs):
        """在发现网关重启时被调用。

        可用于清理上一次启动留下的未结束的状态。

        :kwargs: 相关的属性。其中的datetime已经是pandas.TimeStamp
        :returns: 无
        """
        pass


class StatusParser(ParserBase):

    """分析LogCurrentStatus的类"""

    # LogCurrentStatus行
    re_line_log_status = re.compile(
        r'@2@.*LogCurrentStatus@[^@]+@[^@]+@(?P<content>[^@]+)@.*')

    # LogCurrentStatus首行
    re_line_log_status_begin = re.compile(r'Current Statuses:')

    def __init__(self, parser_name):
        """构造函数 """
        super(StatusParser, self).__init__(parser_name)

        self.status_begin_time = ''  # 状态开始时间。''表示不在状态块中
        self.last_status_time = ''
        self.statuses = list()

    def parse(self, line_time, line_content):
        """分析一行日志

        如果是状态行则更新内部的状态。

        :line_time: 行的时间
        :line_content: 时间之后的内容
        :returns: 匹配上则返回True

        """
        m = self.re_line_log_status.match(line_content)
        if not m:
            return False

        content = m.group('content')
        if self.re_line_log_status_begin.match(content):
            self.__finish_last_status()

            self.status_begin_time = line_time

        self.last_status_time = line_time
        return True

    def finish(self):
        # 结束可能存在的最后一个状态块
        self.__finish_last_status()

        df = pd.DataFrame.from_dict(self.statuses)
        duration = (df['end'] - df['begin']) / pd.Timedelta('1us')
        return Result(summary(duration), df)

    def __finish_last_status(self):
        """ 结束上一个状态块 """
        if self.status_begin_time:
            self.statuses.append({
                'datetime': self.status_begin_time,
                'begin':    self.status_begin_time,
                'end':      self.last_status_time,
            })

            # 清一下状态，下次就不会重复进入
            self.status_begin_time = ''


class RegexParser(ParserBase):
    def __init__(self, parser_name, regex):
        super(RegexParser, self).__init__(parser_name)

        self.details = list()
        self.re = re.compile(regex)

    def parse(self, line_time, line_content):
        m = self.re.match(line_content)
        if not m:
            return False

        d = m.groupdict()
        if not 'datetime' in d:
            # 如果没有datetime，就取日志行的时间
            d['datetime'] = line_time

        self.details.append(d)
        return True

    def finish(self):
        return Result(None, self.details)


class ConnectionParser(ParserBase):
    re_begin_conn = re.compile(
        r'.*@Begin to create server connection of tag \'(?P<gw_id>\w+)\' to (?P<cs_addr>[0-9:.]+)')

    re_connect_ok = re.compile(
        r'.*@sscc::gateway::CsComm(:?::|@)OnConnectOK@.*@Success: CsConnection (?P<conn_id>\d+)\(CS_Connected\) - (?P<gw_addr>[0-9:.]+) to (?P<cs_addr>[0-9:.]+) of tag (?P<gw_id>\w+) to .*')

    re_connect_fail = re.compile(
        r'.*@sscc::gateway::CsComm(:?::|@)OnConnectFail@.*@Failed to create CsConnection of tag (?P<gw_id>\w+)\. WanM error code: (?P<code>\d+):(?P<reason>.+)\. Reconnecting after \d+ seconds\.\.\.@CsConnection (?P<conn_id>\d+)\(CS_DisConnected\) - unknown:0 to (?P<cs_addr>[0-9:.]+) to .*')

    re_connection_close = re.compile(
        r'.*@sscc::gateway::CsComm(:?::|@)OnConnectionClose@.*@CsConnection (?P<conn_id>\d+)\(CS_Closed\) - (?P<gw_addr>[0-9:.]+) to (?P<cs_addr>[0-9:.]+) of tag (?P<gw_id>\w+) to \S+ is closed. WanM error code: (?P<code>\d+):(?P<reason>.+)\. Reconnecting after .*')

    re_connection_logout = re.compile(
        r'.*@sscc::gateway::CsConnection(:?::|@)HandleLogout@.*@Received logout message, code: (?P<code>\d+),\s*(?P<reason>[^@]+)@Connection (?P<conn_id>\d+)\(CS_Connected\) - (?P<gw_addr>[0-9:.]+) to (?P<cs_addr>[0-9:.]+) of tag (?P<gw_id>\w+).*')

    re_wanm_error = re.compile(
        r'.*@sscc::gateway::CsComm.*@WanM ERROR@(?:Ssl )?Connection<(?P<conn_id>\d+)\([^)]+\) - \S+ to (?P<cs_addr>[0-9:.]+)> - (?P<reason>.+)')

    def __init__(self, parser_name='connections'):
        super(ConnectionParser, self).__init__(parser_name)
        #: 网关ID -> 连接信息。连接信息为详细信息的列表
        self.connections = defaultdict(list)
        #: 当前连接上当前活动的连接。连接ID -> 连接信息
        self.active_conns = dict()
        #: 网关ID -> 开始连接时间
        self.begin_time = defaultdict(str)
        #: 记录每个连接首次WanM出错信息
        self.wanm_error_conns = dict()

    def parse(self, line_time, line_content):
        m = self.re_begin_conn.match(line_content)
        if m:
            self.begin_time[m.group('gw_id')] = line_time

            logging.debug(u'    {datetime}: Gateway "{gw_id}" begin to connect {cs_addr}'.format(datetime=line_time, **m.groupdict()))
            return True

        m = self.re_connect_ok.match(line_content)
        if m:
            gw_id = m.group('gw_id')
            conn_id = m.group('conn_id')

            conn = {
                'conn_id' : conn_id,
                'gw_id' : gw_id,
                'begin_time' : self.begin_time[gw_id],
                'connect_time' : line_time,
                'close_time' : '',
                'gw_addr' : m.group('gw_addr'),
                'cs_addr' : m.group('cs_addr'),
                'code' : '',
                'reason' : '',
                'status' : 'connected',
            }
            self.active_conns[conn_id] = conn

            logging.debug(u'    {begin_time}: Gateway "{gw_id}" (#{conn_id}) connected to {cs_addr}'.format(**conn))
            return True

        m = self.re_connect_fail.match(line_content)
        if m:
            gw_id = m.group('gw_id')
            conn_id = m.group('conn_id')

            conn = {
                'conn_id' : conn_id,
                'gw_id' : gw_id,
                'begin_time' : self.begin_time[gw_id],
                'connect_time' : '',
                'close_time' : line_time,
                'gw_addr' : '',
                'cs_addr' : m.group('cs_addr'),
                'code' : 'WanM_' + m.group('code'),
                'reason' : m.group('reason'),
                'status' : 'failed',
            }

            if conn_id in self.wanm_error_conns:
                # 此连接之前已经报错，之前的出错信息才是真正的原因
                conn.update(self.wanm_error_conns[conn_id])

            self.connections[gw_id].append(conn)

            logging.debug(u'    {close_time}: Gateway "{gw_id}" (#{conn_id}) failed to connect to {cs_addr}: {code}, {reason}'.format(**conn))
            return True

        m = self.re_wanm_error.match(line_content)
        if m:
            d = m.groupdict()
            if d['conn_id'] not in self.wanm_error_conns:
                self.wanm_error_conns[d['conn_id']] = {
                    'close_time' : line_time,
                    'code' : 'WanM',
                    'reason' : d['reason'],
                }

            return True

        m = self.re_connection_logout.match(line_content)
        if m:
            self.close_connection(line_time, 'logout:', m.groupdict(), 'logout')
            return True

        m = self.re_connection_close.match(line_content)
        if m:
            self.close_connection(line_time, 'WanM:', m.groupdict(), 'closed')
            return True

        return False

    def close_connection(self, line_time, code_prefix, m, status):
        conn_id = m['conn_id']

        if conn_id in self.active_conns:
            # 本连接前面还没有找到断开原因。
            conn = self.active_conns[conn_id]

            conn.update({
                'close_time' : line_time,
                'code' : code_prefix + (m['code'] if 'code' in m else ''),
                'reason' : m['reason'],
                'status' : status,
            })
            self.connections[conn['gw_id']].append(conn)
            del self.active_conns[conn_id]

            logging.debug(u'    {close_time}: Gateway "{gw_id}" (#{conn_id}) disconnected from {cs_addr}: {code}, {reason}'.format(**conn))

    def finish(self):
        self.on_startup()

        # 按连接ID排序，基本上就是按时间
        for gw_id in self.connections:
            self.connections[gw_id] = sorted(self.connections[gw_id], key=lambda conn: int(conn['conn_id']))

        return self.connections

    def on_startup(self, **kwargs):
        # 每次网关重启，都把之前的连接信息移到connections中
        for conn_id in self.active_conns:
            conn = self.active_conns[conn_id]
            self.connections[conn['gw_id']].append(conn)

        self.active_conns.clear()


class StartupParser(ParserBase):
    """分析网关关闭时间、原因
    """
    re_shutdown_win = re.compile(
        r'.*@cppf::common::StopAppFunc@.*@Catch control event (?P<reason>\w+).*, stopping@.*')

    def __init__(self, parser_name='startups'):
        super(StartupParser, self).__init__(parser_name)
        self.startups = list()
        self.last_startup_time = ''

    def parse(self, line_time, line_content):
        m = self.re_shutdown_win.match(line_content)
        if m:
            self.startups.append({
                'startup_time': self.last_startup_time,
                'shutdown_time' : line_time,
                'shutdown_reason' : m.group('reason'),
            })
            self.last_startup_time = ''
            return True

    def on_startup(self, **kwargs):
        self.last_startup_time = kwargs['datetime']

    def finish(self):
        if self.last_startup_time:  # 最后一次启动没有关闭
            self.startups.append({
                'startup_time': self.last_startup_time,
                'shutdown_time' : '',
                'shutdown_reason' : '',
            })
        return self.startups


class TgwLogParser(object):

    """TGW日志解释类"""

    re_line = re.compile(r'^\](?P<datetime>\d{4}-[^@]+)(?P<content>@.*)$')

    # 网关重启后的第一行
    re_startup = re.compile(r'.*@cppf::common::SzseApp(:?::|@)InitLog@.*')

    def __init__(self, filename, encoding, from_time, to_time):
        """构造函数.

        :filename: 要解释的日志文件名
        :encoding: 日志文件的字符编码。可以为list，会依次用
        :from_time: 日志的开始时间
        :to_time: 日志的结束时间
        """
        self.filename = filename
        self.from_time = from_time
        self.to_time = to_time
        if isinstance(encoding, str):
            self.log_encodings = [encoding,]
        else:
            self.log_encodings = encoding

        self.parsers = (
            StatusParser('status'),
            ConnectionParser('connections'),
            RegexParser(
                'version',
                r''.join([
                    r'.*',
                    r'app started, Version Info: .* (?P<variant>RELEASE|DEBUG) version:(?P<version>.*?) revision:(?P<revision>\d+)',
                    r'.*',
                    r'cmd line:\s*(?P<cmdline>.*)',
                    r'$'
                ])),
            RegexParser(
                'os',
                r'.*osType:(?P<type>.*), osVersion:(?P<version>.*), cpuType:(?P<cpu>.*), cpuBits:(?P<bits>.*), memorySize:(?P<memory>\w+).*'),
            StartupParser(),
        )
        self.first_time = ''
        self.last_time = ''
        self.line_count = 0

    def parse(self, progress_callback=None):
        """解释一个日志文件

        :progress_callback: 进度回调。两个参数：总字节数，当前字节数
        :returns: 无
        """
        last_line_time = None

        logging.info(u'Analyzing log file "{0}"...'.format(self.filename))

        with open(self.filename, 'rb') as f:
            file_size = 0

            if 'seekable' in dir(f):
                # 取文件长度
                f.seek(0, os.SEEK_END)
                file_size = f.tell()
                f.seek(0, os.SEEK_BEGIN)

            line_num = 0
            last_encoding_idx = 0
            encoding_count = len(self.log_encodings)

            for line in f:
                line_num += 1

                # 尝试每种编码，从上次成功的开始尝试
                for i in xrange(encoding_count):
                    try:
                        encoding_idx = (last_encoding_idx + i) % encoding_count
                        line = line.decode(self.log_encodings[encoding_idx])

                        if i > 0:
                            logging.debug(u'    Encoding is changed from {0} to {1}'.format(
                                self.log_encodings[last_encoding_idx], self.log_encodings[encoding_idx]))
                            last_encoding_idx = encoding_idx
                        break
                    except Exception as e:
                        pass
                else:
                    logging.warning(u'  Error decoding line #{0}: {1}'.format(line_num, e))

                m = self.re_line.match(line)
                if not m:
                    continue

                line_time = pd.to_datetime(m.group('datetime'))
                line_content = m.group('content')

                # 根据时间过滤日志行
                t = line_time.time()
                if t < self.from_time:
                    # 跳过未到时间的日志
                    continue
                elif t > self.to_time:
                    # 不再处理时间区间外的日志
                    break

                self.line_count += 1

                if last_line_time is None:   # 首行
                    self.first_time = line_time

                last_line_time = line_time

                m = self.re_startup.match(line_content)
                if m:   # 检测到网关重启
                    logging.debug(u'  Gateway startup at {datetime}'.format(datetime=line_time, **m.groupdict()))

                    d = m.groupdict()
                    d['datetime'] = line_time

                    for parser in self.parsers:
                        parser.on_startup(**d)

                    continue

                for parser in self.parsers:
                    if parser.parse(line_time, line_content):
                        break

            if not last_line_time is None:   # 有末行
                self.last_time = last_line_time


        return self.get_result()

    def get_result(self):
        result = {}
        result['summary'] = {
            'filename'   : self.filename,
            'first_time' : self.first_time,
            'last_time'  : self.last_time,
            'line_count' : self.line_count,
        }

        for parser in self.parsers:
            result[parser.parser_name] = parser.finish()

        logging.info(u'  Done')

        return result


def import_filters(module):
    """把module中的函数变成适合jinja2.env.filters的dict格式

    如 env.filters.update(import_filter(filters))

    参数：
        module: 要导入的模块
    """

    my_filters = {
        name: function
        for name, function in inspect.getmembers(module)
        if inspect.isfunction(function)
    }

    return my_filters


class HtmlReport(object):
    def __init__(self, output_dir):
        """构造函数

        :output_dir: 存放报告的目录
        :returns: 无

        """
        self.output_dir = output_dir

    @staticmethod
    def generate_time_chart(x, y):
        # 生成处理需时的图
        fig, ax = plt.subplots()
        ax.plot(
            x, y,
            marker='.', markersize=3, linestyle='')

        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter('{x:,.0f}'))
        plt.xticks(rotation=15)
        plt.minorticks_on()

        divider = make_axes_locatable(ax)
        ax_hist = divider.append_axes("right", 1.2, pad=0.1, sharey=ax)
        plt.setp(ax_hist.get_yticklabels(), visible=False)
        bins = sorted(set(ax.yaxis.get_majorticklocs()).union(ax.yaxis.get_minorticklocs()))
        ax_hist.hist(y, bins=bins, orientation='horizontal')
        plt.xticks(rotation=30)

        result = chart_util.get_data_uri(fig)
        plt.close(fig)
        return result

    @staticmethod
    def generate_images(result):
        """生成需要的图形
        """

        images = dict()
        images['status'] = HtmlReport.generate_time_chart(
            result['status'].details['begin'],
            (result['status'].details['end'] - result['status'].details['begin']) / pd.Timedelta('1us'))

        return images

    def generate(self, result):
        """生成报表

        :result: 分析结果
        :returns: 无

        """
        logging.info(u'Generating html report in "{0}" ...'.format(self.output_dir))

        if not os.path.exists(self.output_dir):
            logging.info(u'  Creating directory "{0}"...'.format(self.output_dir))
            mkpath(self.output_dir)

        env = jinja2.Environment(loader=jinja2.FileSystemLoader([HTML_TEMPLATE_DIR], encoding='utf-8'))
        env.filters.update(import_filters(filters))

        mytemplate = env.get_template(HTML_TEMPLATE_FILENAME)

        with open(os.path.join(self.output_dir, HTML_REPORT_FILENAME), 'wb') as f:
            f.write(
                mytemplate.render(
                    images=self.generate_images(result), **result).encode('utf-8')
            )

        logging.info(u'  Done')


class TextReport(object):
    def generate(self, result):
        """生成报表

        :result: 分析结果
        :returns: 无

        """
        env = jinja2.Environment(loader=jinja2.FileSystemLoader([TEXT_TEMPLATE_DIR], encoding='utf-8'))
        env.filters.update(import_filters(filters))

        mytemplate = env.get_template(TEXT_TEMPLATE_FILENAME)

        return mytemplate.render(**result)


def main(**args):
    parser = TgwLogParser(
        args['logfile'][0],
        encoding=args['log_encoding'].split(','),
        from_time=pd.to_datetime(args['from'] if args['from'] else '00:00:00').time(),
        to_time=pd.to_datetime(args['to'] if args['to'] else '23:59:59').replace(microsecond=999999).time()
    )

    result = parser.parse()

    if args['html_report']:
        HtmlReport(args['output_dir']).generate(result)
    else:
        args['text_report'] = True

    if args['text_report']:
        print(TextReport().generate(result))


if __name__ == "__main__":
    sys.stdout = codecs.getwriter(locale.getpreferredencoding())(sys.stdout)
    sys.stderr = codecs.getwriter(locale.getpreferredencoding())(sys.stderr)

    parser = argparse.ArgumentParser(
        description=u"""\
TGW日志分析工具""")

    parser.add_argument('-v', '--verbose', action="store_true", dest="verbose", default=False, help=u"显示调试日志")
    parser.add_argument('-q', '--quiet',  action="store_true", dest="quiet", default=False, help=u"只显示警告以上级别的日志")
    parser.add_argument('--version',  action="version", version=VERSION, help=u"显示程序版本号后退出")
    parser.add_argument('-o', '--output', action="store", dest="output_dir", default=DEFAULT_OUTPUT_DIR, help=u"结果存放目录")
    parser.add_argument('-e', '--encoding', action="store", dest="log_encoding", default=DEFAULT_LOG_ENCODING, help=u"日志文件的编码。多个编码以半角逗号分隔")
    parser.add_argument('--html',  action="store_true", dest="html_report", default=False, help=u"生成HTML报告")
    parser.add_argument('--text',  action="store_true", dest="text_report", default=False, help=u"生成文本报告")
    parser.add_argument('-f', '--from',  action="store", dest="from", help=u"只处理此时间之后的数据，HH:MM或HH:MM:SS格式")
    parser.add_argument('-t', '--to',  action="store", dest="to", help=u"只处理此时间之前的数据，HH:MM或HH:MM:SS格式")
    parser.add_argument('logfile', nargs=1, help=u"TGW日志文件路径")

    args = parser.parse_args()

    # 对解释出来的参数进行编码转换
    for k in vars(args):
        v = getattr(args, k)
        if isinstance(v, str):
            setattr(args, k, unicode(v, locale.getpreferredencoding()).strip())
        elif isinstance(v, list):
            setattr(
                args, k,
                [unicode(s, locale.getpreferredencoding()).strip() if isinstance(s, str) else s for s in v])

    # 日志初始化
    log_format = u"%(asctime)s %(levelname)s %(message)s"

    if args.quiet:
        logging.basicConfig(level=logging.WARNING, format=log_format)
    elif args.verbose:
        logging.basicConfig(level=logging.DEBUG, format=log_format)
    else:
        logging.basicConfig(level=logging.INFO, format=log_format)

    main(**vars(args))
