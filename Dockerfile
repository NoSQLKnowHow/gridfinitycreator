FROM continuumio/miniconda3:25.1.1-2

RUN apt-get update -y && \
	apt install -y libgl1-mesa-glx && \
	apt-get clean && \
	rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN conda update conda && \
    conda install conda-forge::cadquery

# copy the requirements file into the image
COPY ./requirements.txt /app/requirements.txt

# switch working directory
WORKDIR /app

# install the dependencies and packages in the requirements file
RUN pip install --no-cache-dir -r requirements.txt 

# copy all local content to the image
COPY . /app

# Where generated files and logs go. The compose files mount a tmpfs (a RAM disk, so the
# short-lived files do not wear out the disk) over /tmpfiles and a volume over /logs; the
# directories exist anyway so that the image also works without those mounts.
ENV GFG_TMP_DIR=/tmpfiles \
    GFG_LOG_DIR=/logs
RUN mkdir -p /tmpfiles /logs

# Report "unhealthy" if the web server stops answering. The start period covers loading CadQuery.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/' % os.environ.get('FLASK_PORT', '5000'), timeout=4)"

# configure the container to run in an executed manner
ENTRYPOINT [ "python" ]

CMD ["gfg_main.py" ]
