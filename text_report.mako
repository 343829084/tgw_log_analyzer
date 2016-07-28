<%!
    import filters
%>
log file name:   ${summary['filename']}
line count:      ${summary['line_count']}
start time:      ${summary['first_time']}
end time:        ${summary['last_time']}
% if version.details:
gateway version: ${version.details[0]['version']}, svn revision: ${version.details[0]['revision']}
% endif

% if os.details:
OS:     ${os.details[0]['type']}, ${os.details[0]['version']}
CPU:    ${os.details[0]['cpu']}(${os.details[0]['bits']})
Memory: ${os.details[0]['memory']}
% endif

Status logs:
count: ${status.summary['count']}  mean: ${status.summary['mean']/1000  |  filters.precision(0)}us  std: ${status.summary['std']/1000    |  filters.precision(0)}us  min: ${status.summary['min']/1000    |  filters.precision(0)}us  max: ${status.summary['max']/1000    |  filters.precision(0)}us  p90: ${status.summary['p90']/1000    |  filters.precision(0)}us

% if version.details:
Gateway startup at:
    % for i in xrange(len(startups)):
${u'{:3d} {:s}'.format(i + 1, startups[i]['datetime'])}
    % endfor
% endif

Connections:
% for gw_id in sorted(connections.keys()): 
    % for idx in xrange(len(connections[gw_id])):
<% conn = connections[gw_id][idx] %>${u'{idx:3d} #{conn_id:<3s} {status:9s} {begin_time:15s} {connect_time:15s} {close_time:15s} {cs_addr:21s} {wanm_errno:5s} {wanm_errmsg}'.format(
    idx=idx+1,                           conn_id=conn['conn_id'],                 status=conn['status'],
    begin_time=conn['begin_time'][-15:], connect_time=conn['connect_time'][-15:], close_time=conn['close_time'][-15:],
    cs_addr=conn['cs_addr'],             wanm_errno=conn['wanm_errno'],           wanm_errmsg=conn['wanm_errmsg'])}
    %endfor
%endfor
