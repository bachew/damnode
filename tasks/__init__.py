from invoke import task


@task
def init(ctx):
    ctx.run('pipenv install')
    ctx.run('pip install -e .')

    # XXX: workaround for: pkg_resources.DistributionNotFound: The 'Click>=6.7' distribution was not found and is required by damnode
    ctx.run('pip install click')
