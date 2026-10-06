import datetime
import logging
import logging.handlers
import os
import re
import secrets
import sys
import tempfile
import threading
import waitress

from flask import Flask, jsonify, make_response, request
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from werkzeug.exceptions import HTTPException

import grid_constants
import gridspec
import job_limiter
import model_builder
import proxy_trust
from generator_loader import load_generators
from generators.common import settings_form
from generators.common.errors import SettingsError
from grid_constants import *
from version import __version__

def secret_key(environ=os.environ):
    """The key Flask uses to sign the session and CSRF tokens.

       Set GFG_SECRET_KEY to keep it fixed. Without it a fresh random key is made each
       time the server starts (this app keeps nothing on the server that depends on it;
       pages left open across a restart are told to reload). It must never be a constant
       in the source: this repository is public, so anyone could forge tokens with it."""
    return environ.get('GFG_SECRET_KEY') or secrets.token_hex(32)

app = Flask(__name__)

# Flask-WTF requires an encryption key
app.config['SECRET_KEY'] = secret_key()

# This app is anonymous and stateless, so the default one-hour expiry of CSRF tokens
# only ever made a page that had been left open fail to submit
app.config['WTF_CSRF_TIME_LIMIT'] = None

# X-Forwarded-* headers are believed only from the proxies named in GFG_TRUSTED_PROXIES (see proxy_trust.py)
trusted_proxies = proxy_trust.parse_proxies(os.environ.get('GFG_TRUSTED_PROXIES'))
app.wsgi_app = proxy_trust.ProxyTrust(app.wsgi_app, trusted_proxies, proxy_trust.parse_hops(os.environ.get('GFG_PROXY_HOPS')))

# Globals
generators = []

# Created at import time (handlers are attached in __main__) so the module also
# works when imported by tests or another WSGI runner, instead of failing on a None logger
logger = logging.getLogger('GFG')

# Bounds how many models are built at once (see job_limiter.py for the settings)
limiter = job_limiter.JobLimiter.from_env()

# What the page sends with a submit so that it can tell when the answer has arrived (generate_feedback.js)
DOWNLOAD_TOKEN = re.compile(r'[A-Za-z0-9_-]{8,64}')

@app.after_request
def echo_download_token(response):
    """Generate is an ordinary form submit and the answer is a file, so the page stays put and the
       browser tells it nothing when the response comes. The page sends a random token with the
       submit; handing it back in a cookie is how it learns the response has arrived.

       The token goes into a response header, so it is only echoed if it is a plain word."""
    token = request.form.get('download_token') if request.method == 'POST' else None
    if token and DOWNLOAD_TOKEN.fullmatch(token):
        # Not HttpOnly: the page has to read it. It is random, secret from nobody, and gone in two minutes.
        response.set_cookie('download_token', token, max_age=120, samesite='Lax', path='/', secure=request.is_secure)
    return response

def new_form(gen):
    """A generator's form, with field ids that are unique on the page (see make_ids_unique)"""
    return settings_form.make_ids_unique(gen.get_form())

def format_mm(value):
    """A length without a pointless ".0": 42.0 -> "42", 39.5 -> "39.5" """
    return f"{value:g}"

def grid_pitch(grid):
    """The grid size as help text puts it, e.g. "42mm for Width and Length, 7mm for Height" """
    if grid.GRID_UNIT_SIZE_X_MM == grid.GRID_UNIT_SIZE_Y_MM:
        size = f"{format_mm(grid.GRID_UNIT_SIZE_X_MM)}mm for Width and Length"
    else:
        size = f"{format_mm(grid.GRID_UNIT_SIZE_X_MM)}mm for Width and {format_mm(grid.GRID_UNIT_SIZE_Y_MM)}mm for Length"
    return f"{size}, {format_mm(grid.HEIGHT_UNITSIZE_MM)}mm for Height"

def grid_cell(grid):
    """The footprint of one grid unit, e.g. "42mm" or "39.5mm by 54.5mm" """
    if grid.GRID_UNIT_SIZE_X_MM == grid.GRID_UNIT_SIZE_Y_MM:
        return f"{format_mm(grid.GRID_UNIT_SIZE_X_MM)}mm"
    return f"{format_mm(grid.GRID_UNIT_SIZE_X_MM)}mm by {format_mm(grid.GRID_UNIT_SIZE_Y_MM)}mm"

def render_index(form_list, constants, errors=(), active_form=''):
    """Render the page. errors are messages to show the user; active_form is the id of
       the generator tab to open (the one that was just submitted), or '' for Home."""
    jinja_env = Environment(loader=FileSystemLoader(["./", os.path.realpath(__file__)]), undefined=StrictUndefined)

    # Fragments (a generator's settings form, its descriptions and help texts) are rendered by
    # a second environment with the same filters and the given variables, so that they can quote
    # the grid in use. It is the plain, lenient kind these fragments have always been rendered
    # with: the settings form probes attributes some widgets do not have. All of them are local files.
    fragment_env = Environment()

    def inner_render(value, context):
        return fragment_env.from_string(value or '').render(context)

    for environment in (jinja_env, fragment_env):
        environment.filters["inner_render"] = inner_render
        environment.filters["mm"] = format_mm
        environment.filters["grid_pitch"] = grid_pitch
        environment.filters["grid_cell"] = grid_cell
    preset = gridspec.preset_name(constants.GRID_UNIT_SIZE_X_MM, constants.GRID_UNIT_SIZE_Y_MM, constants.HEIGHT_UNITSIZE_MM)

    index_template = jinja_env.get_template("templates/index.html.j2")
    # Resolved per request so the copyright never goes stale
    return index_template.render(version=__version__, forms=form_list, errors=list(errors), active_form=active_form,
                            year=datetime.date.today().year,
                            grid=constants, grid_presets=gridspec.PRESETS, grid_preset=preset,
                            grid_is_standard=(preset == gridspec.PRESETS[0][0]),
                            gridsize_x=constants.GRID_UNIT_SIZE_X_MM,
                            gridsize_y=constants.GRID_UNIT_SIZE_Y_MM, gridsize_z=constants.HEIGHT_UNITSIZE_MM)

STALE_PAGE_MESSAGE = "This page is out of date (its session ended or the server was restarted). Reload the page and try again."
UNEXPECTED_ERROR_MESSAGE = "Something went wrong while building that model. Try different settings; the details are in the server log."

def form_errors(form):
    """Flatten a form's validation errors into messages written for the user"""
    messages = []
    for name, field_errors in form.errors.items():
        if name == 'csrf_token':
            if STALE_PAGE_MESSAGE not in messages:
                messages.append(STALE_PAGE_MESSAGE)
            continue

        field = getattr(form, name, None) if name else None
        for text in field_errors:
            messages.append(f"{field.label.text}: {text}" if field is not None else text)
    return messages

def is_background_request():
    """The page's own scripts post the form to refresh the dimensions readout or the
       3D preview; those expect JSON or an STL back, not a whole HTML page"""
    return request.form.get('dimensions') == 'true' or request.form.get('preview') == 'true'

def error_response(errors, status, form_list, constants, active_form='', headers=None):
    if is_background_request():
        response = jsonify({"errors": errors})
        response.status_code = status
    else:
        response = make_response(render_index(form_list, constants, errors, active_form), status)

    for name, value in (headers or {}).items():
        response.headers[name] = value
    return response

@app.errorhandler(Exception)
def unexpected_error(e):
    """Anything not handled explicitly: log it, and tell the user something useful
       instead of showing a bare "Internal Server Error" page"""
    if isinstance(e, HTTPException):
        return e  # 404, 405, ... keep their normal responses
    if app.debug:
        raise e   # let the interactive debugger have it

    logger.exception("Unhandled error while serving %s %s", request.method, request.path)

    forms = [new_form(gen) for gen in generators]
    active_form = next((f.id for f in forms if f.id in request.form), '') if request.method == 'POST' else ''
    return error_response([UNEXPECTED_ERROR_MESSAGE], 500, forms, current_grid(), active_form)

def current_grid():
    """The grid in effect for this request: the standard Gridfinity grid, overridden
       by the saved gridspec cookie when that holds usable values. A missing or
       damaged cookie must never break the page, so it is simply ignored."""
    constants = grid_constants.Grid()

    spec = gridspec.parse_cookie(request.cookies.get(gridspec.COOKIE_NAME))
    if spec:
        constants.GRID_UNIT_SIZE_X_MM, constants.GRID_UNIT_SIZE_Y_MM, constants.HEIGHT_UNITSIZE_MM = spec

    constants.recalculate() # Recalculate derived measures
    return constants

def set_gridspec_cookie(response, constants):
    """Remember the grid for a year. The cookie is only ever read by the server."""
    response.set_cookie(
        gridspec.COOKIE_NAME,
        gridspec.serialize(constants.GRID_UNIT_SIZE_X_MM, constants.GRID_UNIT_SIZE_Y_MM, constants.HEIGHT_UNITSIZE_MM),
        max_age=gridspec.COOKIE_MAX_AGE, samesite='Lax', httponly=True, secure=request.is_secure)

# Handle GET requests for "/"
@app.route('/', methods=['GET'])
def index_get():

    constants = current_grid()

    form_list = []

    # Create a list of forms to pass to Jinja for rendering
    for gen in generators:
        form_list.append(new_form(gen))

    response = make_response(render_index(form_list, constants))

    # (Re)write the cookie when it is missing or was unusable
    if gridspec.parse_cookie(request.cookies.get(gridspec.COOKIE_NAME)) is None:
        set_gridspec_cookie(response, constants)

    return response

def generate(gen, f, constants):
    """Act on a form that passed validation: return the dimensions readout, a preview
       STL, or the file to download"""
    # Dimensions-only request: return the computed real-world dimensions
    # as JSON without generating any geometry (cheap - arithmetic only)
    if request.form.get('dimensions') == 'true' and hasattr(gen, 'dimensions'):
        return jsonify(gen.dimensions(f, constants))

    # Generate an STL with the provided settings
    is_preview = 'preview' in request.form and request.form['preview'] == 'true'
    logger.info("Generating {0} for: {1}{2}".format(f.get_title(), request.remote_addr, " (preview)" if is_preview else ""))
    # Building the model is the expensive step: take a turn, or be told the server is busy.
    # Waitress can say whether the client is still connected (Flask's own server cannot);
    # a client that has gone, e.g. a preview the page replaced with a newer one, is not
    # worth a turn in the queue or a core to build on.
    client_gone = request.environ.get('waitress.client_disconnected')
    with limiter.slot(client_gone), model_builder.stop_when_gone(client_gone):
        response = gen.process(f, constants)

    # If this is a preview request, modify the response to return binary data instead of download
    if is_preview:
        response.headers['Content-Disposition'] = 'inline; filename="preview.stl"'
        response.headers['Content-Type'] = 'application/octet-stream'

    return response

# Handle POST requests for "/"
@app.route('/', methods=['POST'])
def index_post():
    # Use the saved grid size if it was overridden
    constants = current_grid()

    errors = []
    status = 422  # how the request is answered if it ends in errors
    active_form = ''

    # If the request is from the form that specifies the grid size, override these values
    saving_grid = 'advanced_settings' in request.form
    if saving_grid:
        try:
            spec = gridspec.from_form(request.form)
            constants.GRID_UNIT_SIZE_X_MM, constants.GRID_UNIT_SIZE_Y_MM, constants.HEIGHT_UNITSIZE_MM = spec
            constants.recalculate()  # Recalculate derived measures
        except gridspec.GridSpecError as e:
            errors = [str(e)]

    form_list = []

    for gen in generators:
        f = new_form(gen)
        form_list.append(f)

        # Find the generator whose form was submitted
        if f.id not in request.form:
            continue
        active_form = f.id

        if not gen.handles(request, f):
            errors = form_errors(f)
            continue

        try:
            return generate(gen, f, constants)
        except SettingsError as e:
            errors = [str(e)]
        except model_builder.BuildTimeout as e:
            logger.warning("A %s build was stopped: %s", f.get_title(), e)
            errors = [str(e)]
        except model_builder.BuildFailed as e:
            logger.error("Building a %s failed: %s\n%s", f.get_title(), e, e.details)
            errors, status = [UNEXPECTED_ERROR_MESSAGE], 500
        except job_limiter.ClientGone:
            logger.info("Dropped a %s request: its client disconnected before the model was built", f.get_title())
            return make_response('', 499)  # "client closed request"; there is nobody to read it
        except job_limiter.ServerBusy as e:
            logger.warning("Busy: turned away a %s request (%d building, %d waiting)", f.get_title(), limiter.running, limiter.waiting)
            return error_response([str(e)], 503, form_list, constants, active_form, headers={'Retry-After': '5'})

    # Nothing was generated: say why, on the tab the user was working in
    if errors:
        return error_response(errors, status, form_list, constants, active_form)

    response = make_response(render_index(form_list, constants))
    if saving_grid:
        set_gridspec_cookie(response, constants)
    return response

def server_settings(environ=os.environ):
    """Where and how to serve, from the environment: (host, port, debug).

       Production listens on all IPv4 interfaces (a container needs that). Naming the
       address explicitly also avoids the old '*' wildcard, which made the server
       bind IPv6 too and fail to start on a host with IPv6 disabled.

       The debug server includes an interactive debugger that can run code on the
       machine, so it listens on this machine only unless GFG_BIND says otherwise."""
    debug = environ.get('FLASK_DEBUG') == 'True'

    port = int(environ.get('FLASK_PORT', 5000))
    if debug:
        port = int(environ.get('PORT', port))

    host = environ.get('GFG_BIND') or ('127.0.0.1' if debug else '0.0.0.0')
    return host, port, debug

def open_log_file(log_dir, fallback_dir=None):
    """The rotating log handler, writing in the first of log_dir and a temporary directory where a
       file can actually be made: (handler, directory), or (None, None) if there is nowhere (the
       server then logs to the console only).

       A directory that exists is not necessarily writable. A container that runs as an ordinary user
       with a volume that Docker created as root has /logs, but cannot make a file in it."""
    fallback_dir = fallback_dir or os.path.join(tempfile.gettempdir(), 'gridfinitycreator-logs')
    for directory in (log_dir, fallback_dir):
        try:
            os.makedirs(directory, exist_ok=True)
            handler = logging.handlers.RotatingFileHandler(os.path.join(directory, 'access.log'), maxBytes=1000000, backupCount=10)
            return handler, directory
        except OSError:
            continue
    return None, None

class serverFilter():
    """Filter records coming from the server out of the access log"""
    def filter(self, record):
        return (record.name != 'werkzeug') and (record.name != 'waitress')

if __name__ == "__main__":
    host, port, debugMode = server_settings()

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Configure console logger        
    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
    console.setFormatter(formatter)
    console.addFilter(serverFilter())
    root.addHandler(console)

    # Ensure log directory exists in a writable location
    base_dir = os.path.dirname(os.path.realpath(__file__))
    default_log_dir = os.path.join(base_dir, 'logs')
    log_dir = os.environ.get('GFG_LOG_DIR', default_log_dir)

    # Configure rotating file logger (if there is anywhere to write it)
    requested_log_dir = log_dir
    fh, log_dir = open_log_file(requested_log_dir)
    if fh is not None:
        fh.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s: %(message)s')
        fh.setFormatter(formatter)
        fh.addFilter(serverFilter())
        root.addHandler(fh)

    logger = logging.getLogger('GFG')
    if fh is None:
        logger.warning("Cannot write a log file in %s or in the temporary directory: logging to the console only", requested_log_dir)
    elif log_dir != requested_log_dir:
        logger.warning("Cannot write to %s: the log file is in %s instead", requested_log_dir, log_dir)

    try:
        generators = load_generators()
    except Exception as e:
        logger.error(f"Failed to load generators: {e}")
        sys.exit(1)

    # Load CadQuery into the model builder in the background, so the first build is quick
    threading.Thread(target=model_builder.warm_up, daemon=True).start()

    if debugMode:
        logger.info("Started in debug mode, listening on %s:%s", host, port)
        app.run(debug=True, host=host, port=port)
    else:
        logger.info("Started in production mode, listening on %s:%s", host, port)
        waitress.serve(app, host=host, port=port, **job_limiter.server_options(limiter), **proxy_trust.server_options(trusted_proxies))