FROM python:3.11.9-slim

ENV PYTHONHASHSEED=123 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    VECLIB_MAXIMUM_THREADS=1 \
    MPLBACKEND=Agg

WORKDIR /workspace/CITADEL

RUN apt-get update \
    && apt-get install -y --no-install-recommends git git-lfs \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt README.md LICENSE ./
COPY configs ./configs
COPY docs ./docs
COPY hardware ./hardware
COPY notebooks ./notebooks
COPY rtl ./rtl

RUN python -m pip install -U pip \
    && python -m pip install -r requirements.txt

CMD ["python", "-c", "import ast,json; from pathlib import Path; nb=json.loads(Path('notebooks/exact_tcad_all_experiments.ipynb').read_text()); [ast.parse(''.join(c.get('source', []))) for c in nb['cells'] if c.get('cell_type') == 'code']; print('notebook code cells compile')"]
