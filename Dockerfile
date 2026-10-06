FROM continuumio/miniconda3:25.1.1-2

# libgl1 and libglx-mesa0 replace the libgl1-mesa-glx package, which is gone from Debian 13 (the
# next base image may be one). CI builds the image and uses it, which is what checks this.
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends libgl1 libglx-mesa0 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# CadQuery from conda-forge, pinned to the version the tests run against (unpinned, a rebuild can
# bring a new one; that broke this image twice). Its own dependencies (OCP, numpy, nlopt) come with
# it at the versions it declares. conda itself is not updated: that would make two builds of the
# same commit differ.
RUN conda install -y conda-forge::cadquery=2.8.0 && \
    conda clean -afy

# copy the requirements file into the image
COPY ./requirements.txt /app/requirements.txt

# switch working directory
WORKDIR /app

# install the dependencies and packages in the requirements file
RUN pip install --no-cache-dir -r requirements.txt

# copy all local content to the image
COPY . /app

# Compile now: the filesystem may be read-only at run time, and compiled files that exist are used
# even when Python is told not to write any.
RUN python -m compileall -q /app

# An ordinary user to run the server as (the compose files use the same uid)
RUN groupadd --gid 1000 gfg && \
    useradd --uid 1000 --gid 1000 --no-create-home --shell /usr/sbin/nologin gfg

# Where generated files and logs go. The compose files mount a tmpfs (a RAM disk, so the
# short-lived files do not wear out the disk) over /tmpfiles and a volume over /logs; the
# directories exist anyway, and belong to the server's user, so that the image also works without
# those mounts. (A volume Docker makes by itself starts out as a copy of its directory here.)
# HOME is somewhere writable for any library that wants a cache directory; PYTHONDONTWRITEBYTECODE
# because the root filesystem may be read-only.
ENV GFG_TMP_DIR=/tmpfiles \
    GFG_LOG_DIR=/logs \
    HOME=/tmp \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN mkdir -p /tmpfiles /logs && chown gfg:gfg /tmpfiles /logs

USER 1000:1000

# Report "unhealthy" if the web server stops answering. The start period covers loading CadQuery.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/' % os.environ.get('FLASK_PORT', '5000'), timeout=4)"

# configure the container to run in an executed manner
ENTRYPOINT [ "python" ]

CMD ["gfg_main.py" ]
