FROM python:3.11.15-slim-bookworm@sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=UTC \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=123 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    VECLIB_MAXIMUM_THREADS=1 \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    VIRTUAL_ENV=/opt/citadel-venv \
    PATH=/opt/citadel-venv/bin:$PATH

WORKDIR /workspace/CITADEL

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git git-lfs \
    && git config --system --add safe.directory /workspace/CITADEL \
    && rm -rf /var/lib/apt/lists/*

COPY .python-version pyproject.toml uv.lock requirements.txt environment.yml README.md LICENSE ./

RUN python -m pip install --no-cache-dir uv==0.12.13 \
    && uv venv "$VIRTUAL_ENV" --python /usr/local/bin/python \
    && uv sync --active --frozen --no-dev --no-install-project

COPY configs ./configs
COPY docs ./docs
COPY hardware ./hardware
COPY notebooks ./notebooks
COPY reproducibility ./reproducibility
COPY rtl ./rtl
COPY scripts ./scripts
COPY tests ./tests
COPY APPLE_DATA_GENERATION ./APPLE_DATA_GENERATION
COPY TELEMETRY_COLLECTION_SCRIPTS ./TELEMETRY_COLLECTION_SCRIPTS
COPY data/README.md data/external_sources.json ./data/

RUN python -m compileall -q scripts tests APPLE_DATA_GENERATION \
    && python -c "import ast,json; from pathlib import Path; nb=json.loads(Path('notebooks/exact_tcad_all_experiments.ipynb').read_text()); [ast.parse(''.join(c.get('source', []))) for c in nb['cells'] if c.get('cell_type') == 'code']; print('notebook code cells compile')"

EXPOSE 8888

CMD ["python", "-m", "jupyterlab", "--ip=0.0.0.0", "--port=8888", "--no-browser", "--allow-root"]
