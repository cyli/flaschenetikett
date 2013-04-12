"""
Sample klein app, no decorators
"""

from klein import route


@route('/')
def hello_world(request):
    """
    Hi to the world
    """
    return "Hello world!"


@route('/hello/<string:your_name>/')
def a_more_specific_hello(request, your_name):
    """
    Hi to whomever is specified the URL
    """
    return "Hello, {0}!".format(your_name)
