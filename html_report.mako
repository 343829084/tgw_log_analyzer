<%!
    import filters
%>
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>交易网关日志分析结果</title>
    <style type="text/css" media="screen">
        td.warning {
            background: #FF8080;
        }
        td, th {
            border: 1px solid black;
        }

        .center {
            text-align: center;
        }

        table {
            border-collapse: collapse;
        }
    </style>
</head>
<body>
    <h1>交易网关日志分析结果</h1>

    <h2>基本信息</h2>
    
    <table>
        <tr>
            <th>日志文件名</th>
            <td>${summary['filename']}</td>
        </tr>
        <tr>
            <th>日志行数</th>
            <td>${summary['line_count']}</td>
        </tr>
        <tr>
            <th>日志开始时间</th>
            <td>${summary['first_time']}</td>
        </tr>
        <tr>
            <th>日志结束时间</th>
            <td>${summary['last_time']}</td>
        </tr>
        % if version.details:
        <tr>
            <th>网关版本</th>
            <td>${version.details[0]['version']}，svn revision：${version.details[0]['revision']}</td>
        </tr>
        % endif
    </table>

    % if os.details:
    <h2>系统信息</h2>
    <table>
        <tr>
            <th>操作系统</th>
            <td>${os.details[0]['type']}，${os.details[0]['version']}</td>
        </tr>
        <tr>
            <th>CPU</th>
            <td>${os.details[0]['cpu']}（${os.details[0]['bits']}）</td>
        </tr>
        <tr>
            <th>内存</th>
            <td>${os.details[0]['memory']}</td>
        </tr>
    </table>
    % endif

    <h2>网关状态日志耗时分析</h2>
    <p>在日志中，共有 ${status.summary['count'] | filters.thousands_sep} 次状态日志，情况如下：</p>
    <table class='center'>
        <tr>
            <th rowspan="2">状态日志数</th>
            <th colspan="5">耗时（毫秒）</th>
        </tr>
        <tr>
            <th>平均耗时</th>
            <th>标准差</th>
            <th>最快</th>
            <th>最慢</th>
            <th>90%</th>
        </tr>
        <tr>
            <td>${status.summary['count'] | filters.thousands_sep}</td>
            <td ${'class="warning"' if status.summary['mean'] >= 100000 else ''}>${status.summary['mean']/1000 | filters.precision(3), filters.thousands_sep}</td>
            <td>${status.summary['std']/1000 | filters.precision(3), filters.thousands_sep}</td>
            <td>${status.summary['min']/1000 | filters.precision(3), filters.thousands_sep}</td>
            <td ${'class="warning"' if status.summary['max'] >= 500000 else ''}>${status.summary['max']/1000 | filters.precision(3), filters.thousands_sep}</td>
            <td ${'class="warning"' if status.summary['p90'] >= 500000 else ''}>${status.summary['p90']/1000 | filters.precision(3), filters.thousands_sep}</td>
        </tr>
    </table>

    % if len(startups) > 0:
    <h2>网关启动时间</h2>
    <table>
        <tr>
            <th>编号</th>
            <th>启动时间</th>
            <th>停止时间</th>
            <th>停止原因</th>
        </tr>
        % for i in xrange(len(startups)):
        <tr>
            <td>${i + 1}</td>
            <td>${filters.format_time(startups[i]['startup_time'])}</td>
            <td>${filters.format_time(startups[i]['shutdown_time'])}</td>
            <td>${startups[i]['shutdown_reason']}</td>
        </tr>
        % endfor
    </table>
    % endif

    <h2>网关连接情况</h2>
    % for gw_id in sorted(connections.keys()):
        <h3>网关 ${gw_id}</h3>
        <table>
            <% conns = connections[gw_id] %>
            <tr>
                <th>序号</th>
                <th>WanM ID</th>
                <th>状态</th>
                <th>开始时间</th>
                <th>连接建立时间</th>
                <th>连接断开时间</th>
                <th>TCS地址</th>
                <th>WanM错误码</th>
                <th>WanM错误信息</th>
            </tr>
            % for idx in xrange(len(conns)):
                <% conn = conns[idx] %>
                <tr>
                    <td>${idx+1}</td>
                    <td>${conn['conn_id']}</td>
                    <td>${{
                            'connected':u'连接后未断开',
                            'failed':u'连接失败',
                            'closed':u'连接后断开',
                        }[conn['status']]}</td>
                    <td>${filters.format_time(conn['begin_time'])}</td>
                    <td>${filters.format_time(conn['connect_time'])}</td>
                    <td>${filters.format_time(conn['close_time'])}</td>
                    <td>${conn['cs_addr']}</td>
                    <td>${conn['wanm_errno']}</td>
                    <td>${conn['wanm_errmsg']}</td>
                </tr>
            % endfor
        </table>
    %endfor
</body>
</html>
