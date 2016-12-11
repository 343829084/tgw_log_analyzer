# vim: set fileencoding=utf-8 tabstop=4 expandtab shiftwidth=4 softtabstop=4:
import base64
import StringIO

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def get_data_uri(fig, fmt='png'):
    """返回一个matplotlib.figure对象的data-uri串

    可以用于内联图形。
    """
    output = StringIO.StringIO()
    fig.savefig(output, format=fmt)
    return "data:image/{format};base64,{content}".format(
        format=fmt,
        content=base64.b64encode(output.getvalue()))

