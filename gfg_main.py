import datetime
import logging
import logging.handlers
import os
import sys
import threading
import waitress

from flask import Flask, jsonify, make_response, request
from jinja2 import Environment, FileSystemLoader, StrictUndefined, Template
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

import grid_constants
import gridspec
import job_limiter
import model_builder
from generator_loader import load_generators
from generators.common.errors import SettingsError
from grid_constants import *
from version import __version__

app = Flask(__name__)

# Flask-WTF requires an encryption key - the string can be anything
app.config['SECRET_KEY'] = 'hPqPfz!y=moJ!MVO{*tqQO$_Itoo:'

# This app is anonymous and stateless, so the default one-hour expiry of CSRF tokens
# only ever made a page that had been left open fail to submit
app.config['WTF_CSRF_TIME_LIMIT'] = None

# Apply proxy fix
app.wsgi_app = ProxyFix(
    app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
)

# Globals
generators = []

# Created at import time (handlers are attached in __main__) so the module also
# works when imported by tests or another WSGI runner, instead of failing on a None logger
logger = logging.getLogger('GFG')

# Bounds how many models are built at once (see job_limiter.py for the settings)
limiter = job_limiter.JobLimiter.from_env()

def inner_render(value, context):
    return Template(value).render(context)

def render_index(form_list, constants, errors=(), active_form=''):
    """Render the page. errors are messages to show the user; active_form is the id of
       the generator tab to open (the one that was just submitted), or '' for Home."""
    jinja_env = Environment(loader=FileSystemLoader(["./", os.path.realpath(__file__)]), undefined=StrictUndefined)
    jinja_env.filters["inner_render"] = inner_render

    index_template = jinja_env.get_template("templates/index.html.j2")
    # Resolved per request so the copyright never goes stale
    return index_template.render(version=__version__, forms=form_list, errors=list(errors), active_form=active_form,
                            year=datetime.date.today().year,
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

    forms = [gen.get_form() for gen in generators]
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
        form_list.append(gen.get_form())

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
    # Building the model is the expensive step: take a turn, or be told the server is busy
    with limiter.slot():
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
        f = gen.get_form()
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

class serverFilter():
    """Filter records coming from the server out of the access log"""
    def filter(self, record):
        return (record.name != 'werkzeug') and (record.name != 'waitress')

if __name__ == "__main__":
    portNum = 5000 if 'FLASK_PORT' not in os.environ else os.environ['FLASK_PORT']
    debugMode = False if 'FLASK_DEBUG' not in os.environ else (os.environ['FLASK_DEBUG'] == 'True')

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

    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError:
        log_dir = os.path.join('/tmp', 'gridfinitycreator-logs')
        os.makedirs(log_dir, exist_ok=True)

    # Configure rotating file logger
    fh = logging.handlers.RotatingFileHandler(os.path.join(log_dir, 'access.log'), maxBytes=1000000, backupCount=10)
    fh.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s: %(message)s')
    fh.setFormatter(formatter)
    fh.addFilter(serverFilter())
    root.addHandler(fh)

    logger = logging.getLogger('GFG')

    try:
        generators = load_generators()
    except Exception as e:
        logger.error(f"Failed to load generators: {e}")
        sys.exit(1)

    # Load CadQuery into the model builder in the background, so the first build is quick
    threading.Thread(target=model_builder.warm_up, daemon=True).start()

    if debugMode:
        logger.info("Started in debug mode")
        port = int(os.environ.get('PORT', portNum))
        app.run(debug=True, host='0.0.0.0', port=port)
    else:
        logger.info("Started in production mode")
        waitress.serve(app, listen='*:' + str(portNum), threads=job_limiter.server_threads(limiter))