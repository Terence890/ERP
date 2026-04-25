"""Database initialisation and helper utilities for the ERP application."""
import sqlite3
import click
from flask import current_app, g
from flask.cli import with_appcontext


def get_db():
    """Return the active database connection, opening one if necessary."""
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['DATABASE'], detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(_=None):
    """Close the active database connection at the end of the application context."""
    db_conn = g.pop('db', None)
    if db_conn is not None:
        db_conn.close()


def init_db():
    """Initialise the database by executing the bundled schema SQL script."""
    db_conn = get_db()
    with current_app.open_resource('schema.sql') as f:
        db_conn.executescript(f.read().decode('utf8'))


@click.command('init-db')
@with_appcontext
def init_db_command():
    """CLI command: drop and re-create all tables from schema.sql."""
    init_db()
    click.echo('Initialized the database.')


def init_app(app):
    """Register database teardown and CLI commands with *app*."""
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
