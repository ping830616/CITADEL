FROM python:3.11.9-slim

ENV PYTHONHASHSEED=123 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    VECLIB_MAXIMUM_THREADS=1 \
    MPLBACKEND=Agg

WORKDIR /workspace/EXACT-TCAD

RUN apt-get update \
    && apt-get install -y --no-install-recommends git make \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements.txt README.md LICENSE Makefile ./
COPY configs ./configs
COPY docs ./docs
COPY exact ./exact
COPY hardware ./hardware
COPY rtl ./rtl
COPY scripts ./scripts
COPY tests ./tests

RUN python -m pip install -U pip \
    && python -m pip install -e ".[dev]"

CMD ["make", "reproduce-smoke"]
