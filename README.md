[![All Contributors](https://img.shields.io/github/all-contributors/jeroen94704/gridfinitycreator?color=ee8449&style=plastic)](#contributors)
[![Server status](https://img.shields.io/website?url=https%3A%2F%2Fgridfinity.bouwens.co&up_message=Online&down_message=Offline&style=plastic&label=gridfinity.bouwens.co&link=https%3A%2F%2Fgridfinity.bouwens.co)](https://gridfinity.bouwens.co)


# Gridfinity Creator

This application generates STL or STEP files of configurable Gridfinity compatible components. For example, for the standard divider bin you can specify width, length, height, number of compartments (in both directions) and whether or not you want a stacking lip, magnet holes, screw holes, curved scoop surface and/or one or more label tabs. Here are some of the possible bins you can create in this way:
![gridfinity-options](https://github.com/jeroen94704/gridfinitycreator/assets/548463/1577deb0-edc6-48d9-9a54-75fe3ecd335c)
The total number of possible combinations with those options is beyond one million, which is why the 3D models are dynamically created and not pre-calculated.

## Available components

There are currently a few components available, listed below. Other components are in the works.

- Baseplate: Basic baseplate without screws, magnets or weighting.
- Divider bin: Standard divider bin very similar to Zack's original design. 
- Light bin: A light version of the normal Gridfinity bin that saves plastic and offers more room. This means there is no room for magnets and/or screws
- Solid bin: A completely filled solid Gridfinity bin which can be used as a starting point for custom bins
- Holey bin: A solid bin with a grid of holes of user-defined shape, size and depth. Includes option for a keepout-area around each hole

## Online generator

If you don't know how to run your own server (or simply don't want to), there should be an instance of the generator running at https://gridfinity.bouwens.co. No uptime guarantees, but it has been running since early 2023 and seems stable enough, even with the occasional spike in load.

## Installation and deployment

The generator runs as a web-application in a docker container. To run your own instance, perform the following steps from the command line:

- [Download and unzip the code](https://github.com/jeroen94704/gridfinitycreator/releases/latest) or clone the repository: `git clone https://github.com/jeroen94704/gridfinitycreator`
- cd into the source directory
- Build the image and start the server: `./deploy.sh` (may need to prefix this with 'sudo')

Now you can access the application by opening a browser and navigating to <ip-address-of-server>:5000, e.g.

`http://192.168.1.100:5000/`

Notes:

- `./deploy.sh` builds the image itself; `./build.sh` is only needed if you want to build the image without starting it.
- The compose file attaches the container to an external docker network called `proxy` (used by the reverse proxy set-up below). `./deploy.sh` creates that network if it does not exist yet.
- Logs are kept in `./data/gridfinitycreator/logs`. To keep them elsewhere, set `DATA_ROOT` in `.env.container`.
- Your local settings live in `.env.container`, which `./deploy.sh` creates from `.env.container.template` on a first start. It is not kept in git, so it is yours to edit. (If you update an existing checkout that still tracked it, move your copy aside before `git pull` and put it back after.)
- The server runs as an ordinary user (uid 1000), so the log directory has to be writable by that user. `./deploy.sh` creates it for you, owned by you; if your user is not uid 1000 it tells you how to hand the directory over. If the server cannot write there it still starts, and logs to a temporary directory (lost when the container is) with a warning in `docker logs`.
- The scripts use `docker compose` (the Compose plugin) when it is installed and fall back to the older `docker-compose`.

### Configuration

Everything has a default that works for a small private network, so none of this is required. The settings are environment variables, which you can add under `environment:` in the compose file.

| Variable | Default | Meaning |
|---|---|---|
| `FLASK_PORT` | `5000` | Port the server listens on |
| `GFG_BIND` | `0.0.0.0` (`127.0.0.1` in debug mode) | Address the server listens on |
| `GFG_SECRET_KEY` | random at each start | Key used to sign sessions and form tokens. Set it to keep it fixed across restarts; a page left open across a restart is otherwise told to reload |
| `GFG_TMP_DIR` | `/tmpfiles` in the image | Where generated files are written until they are downloaded (the compose files mount a RAM disk here) |
| `GFG_LOG_DIR` | `/logs` in the image | Where the log files go |
| `GFG_MAX_JOBS` | `2` | Models built at the same time |
| `GFG_MAX_QUEUE` | `4` | Further requests allowed to wait for a turn; anything beyond that is told the server is busy (HTTP 503) |
| `GFG_QUEUE_TIMEOUT` | `120` | Seconds a waiting request is kept waiting |
| `GFG_THREADS` | max jobs + queue + 4 | Server threads (never fewer than max jobs + queue + 1, so the page stays responsive while models are building) |
| `GFG_BUILD_TIMEOUT` | `300` | Seconds a model may take to build before it is stopped |
| `GFG_MAX_DIVIDER_SEGMENTS` | `300` | Largest divider-bin layout allowed, in divider wall segments (about 12 x 12 compartments) |
| `GFG_MAX_LIGHT_DIVIDER_SEGMENTS` | `150` | The same limit for the light bin, which does more work per segment |
| `GFG_MAX_HOLES` | `600` | Most holes a holey bin may have |
| `GFG_TRUSTED_PROXIES` | none | Reverse proxies whose `X-Forwarded-For`, `-Proto` and `-Host` headers are believed: addresses or networks, separated by commas (for example `172.18.0.0/16`). Leave it empty when visitors connect directly. See [Reverse proxy](#reverse-proxy) |
| `GFG_PROXY_HOPS` | `1` | How many proxies a request passes through before it reaches the server (only matters with `GFG_TRUSTED_PROXIES`) |

If you expose an instance to the internet, lower the limits (`GFG_MAX_QUEUE`, `GFG_QUEUE_TIMEOUT`, `GFG_BUILD_TIMEOUT` and the three `GFG_MAX_*` limits) so one visitor cannot keep the server busy for long.

### Security

The container runs as an ordinary user (uid 1000) on a read-only filesystem with no extra privileges and no Linux capabilities. It writes only to two size-limited RAM disks (`/tmpfiles` for the generated files and `/tmp`) and to the `/logs` volume. The compose files set this up, and CI starts the image exactly like that and uses it.

### Resource needs

Models are built in separate processes so that the web page stays responsive while they are being generated. An idle instance uses roughly 1 GB of memory (the web server and a warm copy of CadQuery that new builds start from); each model being built at the same time needs a few hundred MB more, more for the largest ones. Allow about 2 GB for the default settings, and fewer concurrent builds (`GFG_MAX_JOBS`) on a smaller machine. The compose files cap the container at 3 GB; set `GFG_MEM_LIMIT` (for example `GFG_MEM_LIMIT=4g` in `.env.container`) to change that. A normal bin takes about a second to build; the largest allowed ones take about a minute.

## Portainer deployment

If you want to deploy this app with Portainer, use the Git repository and a stack that points to the simplified compose file.

- Repository URL: `https://github.com/NoSQLKnowHow/gridfinitycreator.git`
- Repository reference: `feature/config-library` (or `main` for the main branch)
- Compose path: `docker-compose.portainer.yml`

This stack file needs no environment file and no external `proxy` network.

The server runs as uid 1000, so the `gridfinitycreator_logs` volume has to belong to that user. A volume created fresh starts out that way. One created by an earlier version of the image (which ran as root) belongs to root; the server then logs to a temporary directory instead and says so in the container's log. To hand the volume over:

`docker run --rm -v gridfinitycreator_logs:/logs alpine chown -R 1000:1000 /logs`

If your Portainer UI only shows a single repository reference field, use `https://github.com/NoSQLKnowHow/gridfinitycreator.git#feature/config-library`.

## Debug mode

The deploy script results in the server running in production mode using the [Waitress WSGI server](https://flask.palletsprojects.com/en/2.2.x/deploying/waitress/). This is good for performance, but if you want to debug the code, start the server using the "./debug.sh" script instead of "./deploy.sh". This will make the server start itself using the built-in Flask server, which has convenient debugging features.

The debug server includes an interactive debugger that can run code on the machine, so it is only published on the host's own loopback address (`http://127.0.0.1:5001/`). Do not publish it on a network interface.

## Development

Run the tests with `pip install cadquery==2.8.0 -r requirements-dev.txt` followed by `pytest`. They drive the real application, including real CadQuery geometry, so CadQuery must be installed (the version the image uses); the whole suite takes about a minute. If Node.js is installed they also run the unit tests of the browser-side scripts (`tests/js`).

Dependencies are pinned to the versions the tests run against (`requirements.txt`; CadQuery in the `Dockerfile`, where conda installs it, and in `.github/workflows/ci.yml`; a test checks that they agree). Dependabot proposes updates to the pins, the base image and the CI actions.

CI (`.github/workflows/ci.yml`) lints for real bugs (`ruff.toml`), runs the tests, then builds the image, runs the tests inside it, starts it hardened as described above and uses it (`tools/smoke_test.py`, which you can also point at any running instance: `python tools/smoke_test.py http://host:5000`).

## Reverse proxy

Because I use Traefik myself I included the Traefik labels I use in the docker-compose file. If you want to use Traefik, uncomment them and comment out the "ports" section. You will also need to fill in your domain in the .env.container file. 

A proxy that ends the visitor's HTTPS connection tells the server who the visitor was and that they used https in `X-Forwarded-*` headers. The server believes those headers only from the proxies you name in `GFG_TRUSTED_PROXIES`: anyone who can reach the server directly can send the same headers, and would otherwise be able to choose the address that ends up in the log. Headers from any other peer are discarded, and `X-Forwarded-Prefix` is never used (the server does not run under a path prefix). Without the setting the server sees the proxy's address, logs it for every visitor, and does not mark its cookies `Secure`.

Name the proxy by its address, or by the network it is on (`docker network inspect proxy` shows the subnet of the `proxy` network the compose file uses, for example `GFG_TRUSTED_PROXIES=172.18.0.0/16`). With a chain of proxies (a CDN in front of Traefik, say), list the one that talks to the server and set `GFG_PROXY_HOPS` to the length of the chain. A typo in either setting stops the server from starting, with the reason in `docker logs`.

I have no experience with other reverse proxy methods (Apache, nginx, Helm, etc), so if anyone creates instructions for setting up GridfinityCreator with any of those I'd happily accept the pull-request.

## Contributors

<!-- ALL-CONTRIBUTORS-LIST:START - Do not remove or modify this section -->
<!-- prettier-ignore-start -->
<!-- markdownlint-disable -->
<table>
  <tbody>
    <tr>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/NoSQLKnowHow"><img src="https://avatars.githubusercontent.com/u/2966377?v=4?s=100" width="100px;" alt="Kirk Kirkconnell"/><br /><sub><b>Kirk Kirkconnell</b></sub></a><br /><a href="#ideas-NoSQLKnowHow" title="Ideas, Planning, & Feedback">🤔</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/wug-ge"><img src="https://avatars.githubusercontent.com/u/75441883?v=4?s=100" width="100px;" alt="wug-ge"/><br /><sub><b>wug-ge</b></sub></a><br /><a href="#bug-wug-ge" title="Bug reports">🐛</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://bluelight.co"><img src="https://avatars.githubusercontent.com/u/1222984?v=4?s=100" width="100px;" alt="Chase Bolt"/><br /><sub><b>Chase Bolt</b></sub></a><br /><a href="#bug-chasebolt" title="Bug reports">🐛</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/dseifert"><img src="https://avatars.githubusercontent.com/u/94670?v=4?s=100" width="100px;" alt="Daniel Seifert"/><br /><sub><b>Daniel Seifert</b></sub></a><br /><a href="#bug-dseifert" title="Bug reports">🐛</a> <a href="#code-dseifert" title="Code">💻</a></td>
    </tr>
  </tbody>
</table>

<!-- markdownlint-restore -->
<!-- prettier-ignore-end -->

<!-- ALL-CONTRIBUTORS-LIST:END -->

## Donate

If you find this project useful a small donation is much appreciated (but by no means required or expected): https://ko-fi.com/jeroen94704

## License

GridfinityCreator © 2023 by Jeroen Bouwens is licensed under CC BY-NC-SA 4.0. To view a copy of this license, visit http://creativecommons.org/licenses/by-nc-sa/4.0/
