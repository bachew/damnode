# -*- coding: utf-8 -*-
import click
import traceback
from click import ClickException
from damnode.core import Damnode


class DamnodeCommand(click.Group):
    def invoke(self, ctx):
        damnode = Damnode()
        ctx.obj = damnode
        try:
            return super(DamnodeCommand, self).invoke(ctx)
        except (ClickException, click.Abort):
            raise
        except Exception as e:
            if damnode.verbose:
                traceback.print_exc()
                raise
            else:
                msg = '\n'.join([str(e), 'Provide -v to see full stack trace'])
                raise ClickException(msg)


@click.command(cls=DamnodeCommand)
@click.help_option('-h', '--help')
@click.option('-v', '--verbose',
              is_flag=True,
              default=False,
              help='Verbose output')
@click.pass_obj
def main(damnode, verbose):
    damnode.verbose = verbose


@main.command()
@click.help_option('-h', '--help')
@click.option('-i', '--index',
              multiple=True,
              help='Node index directory or URL (default: {!r})'.format(Damnode.default_index))
@click.option('--no-cache', is_flag=True,
              help='Do not cache downloads')
@click.option('--cache-dir',
              help='Directory to cache downloads (default: {!r})'.format(Damnode.default_cache_dir))
@click.option('--prefix', help='Prefix directory to install to (default: {!r})'.format(Damnode.default_prefix))
@click.argument('hint', required=False)
@click.pass_obj
def install(damnode, index, no_cache, cache_dir, prefix, hint):
    '''
    Install Node of latest version or from the given HINT, it is detected as follows:

    \b
    1. Exact version (e.g. 7.9.0, v7.10.0), v doesn't matter
    2. Partial version (e.g. v8, 8.1), latest version will be selected
    3. Package file (e.g. ~/Downloads/node-v6.11.0-darwin-x64.tar.gz)
    4. Package URL (e.g. https://nodejs.org/dist/v4.8.3/node-v4.8.3-linux-x64.tar.gz)
    5. Packages directory (e.g. /var/www/html/node/v5.12.0/)
    6. Version URL (e.g. https://nodejs.org/dist/v5.12.0/)

    Only tar.gz and zip formats are supported.
    '''
    if index:
        damnode.prepend_index(index)

    if no_cache:
        damnode.enable_cache = False

    if cache_dir:
        damnode.cache_dir = cache_dir

    if prefix:
        damnode.prefix = prefix

    damnode.install(hint)
