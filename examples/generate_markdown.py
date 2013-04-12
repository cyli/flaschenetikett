"""
Generate Markdown documentation based on routes parsed using
:mod:`flaschenetikett`
"""
from optparse import OptionParser
import itertools

import flaschenetikett


def write_markdown(routes, filehandle):
    """
    Writes the REST documentation to a file, in Markdown format

    :param routes: an iterable of :class:`flaschenetikett.Route` to document
    :param filehandle: an open file handle to write to

    :return: None
    """
    for route in routes:
        # title, path, and methods
        filehandle.write('## {title}\n'.format(title=route.title))
        filehandle.write('__{methods}: {path}__\n'.format(
            methods=' | '.join(route.methods).upper(),
            path=route.path))

        # URL parameter types, sorted alphabetically
        for param in sorted(route.path_types.iteritems(), lambda x: x[0]):
            filehandle.write('\n * `{0}`: {1}\n'.format(*param))

        # decorators
        for decorator in route.decorators:
            if decorator['name'] == 'headered':
                filehandle.write('\n_X-Arbitrary-Header_: Here is a header!\n')

        # docstring
        filehandle.write('\n' + route.docstring + '\n\n')


def document_modules(module_names, filehandle, group_by_module=False):
    """
    Generate documentation altogether or grouped by module
    """
    modules = [flaschenetikett.import_module(name) for name in module_names]
    if group_by_module:
        for module in modules:
            filehandle.write('#{name}\n\n'.format(name=module.__name__))

            filehandle.write(module.__doc__ + '\n\n')

            routes = flaschenetikett.routes_from_module(module)
            routes = sorted(routes, key=lambda route: len(route.path))
            write_markdown(routes, filehandle)

    else:
        routes = itertools.chain(*[flaschenetikett.routes_from_module(module)
                                   for module in modules])
        routes = sorted(routes, key=lambda route: len(route.path))
        write_markdown(routes, filehandle)


def cli():
    """
    Command line script function.
    """
    parser = OptionParser(usage="Usage: %prog [options] module [module...]")

    parser.add_option("-o", "--output", dest="filename", metavar="FILE",
                      default="rest.md",
                      help="File to write to.  Defaults to rest.md.")
    parser.add_option("-m", "--group-by-module", dest="group_by_module",
                      action="store_true", default=False)

    options, args = parser.parse_args()

    if len(args) < 1:
        parser.error("Need a module to parse")

    with open(options.filename, 'wb') as filehandle:
        document_modules(args, filehandle, options.group_by_module)


if __name__ == "__main__":
    cli()
