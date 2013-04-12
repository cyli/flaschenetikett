"""
Sample klein app with a decorator
"""
from functools import wraps
from klein import route


def headered(decoratee):
    """
    Set arbitrary headers on the request.
    """
    @wraps(decoratee)
    def decorate(request, *args, **kwargs):
        request.setHeader('X-Arbitary-Header', 'Here is a header!')
        return decoratee(*args, **kwargs)
    return decorate


@route('/headerless/')
def say_hello_without_headers():
    """
    Hi, there are no headers
    """
    return "These are not the headers you're looking for."


@route('/headers/')
@headered
def a_more_specific_hello(your_name):
    """
    Hi to whomever is specified the URL
    """
    return "There is a header here!"
