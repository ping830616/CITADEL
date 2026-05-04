# CITADEL Paper Figures And Tables

This file lists the PNG assets generated for the CITADEL manuscript and gives Overleaf-ready snippets.

## PNG Assets

- `docs/figures/fig_citadel_overview.png`
- `docs/figures/fig_slm_closed_loop.png`
- `docs/figures/fig_citadel_method_repo_map.png`
- `docs/figures/fig_cintas_datapath.png`
- `docs/figures/table_prior_slm_engines.png`
- `docs/figures/table_design_space_variables.png`

## Suggested Intro Figure

```latex
\begin{figure*}[!t]
\centering
\includegraphics[width=0.95\textwidth]{figs/fig_citadel_overview.png}
\caption{CITADEL overview. Benign telemetry is calibrated, ranked through causal structure learning, compiled into fixed-point CINTAS scoring, and checked for benign drift during field operation.}
\label{fig:citadel_overview}
\end{figure*}
```

## Suggested Background Figure

```latex
\begin{figure}[!t]
\centering
\includegraphics[width=\columnwidth]{figs/fig_slm_closed_loop.png}
\caption{Closed-loop SLM workflow. CITADEL sits in the edge analytics path and checks whether the deployed CINTAS reference remains valid as benign telemetry changes.}
\label{fig:slm_closed_loop}
\end{figure}
```

## Suggested Method Figures

```latex
\begin{figure*}[!t]
\centering
\includegraphics[width=0.95\textwidth]{figs/fig_citadel_method_repo_map.png}
\caption{CITADEL methodology and reproducible GitHub artifacts. Each method step maps to a script, configuration file, manifest, or RTL artifact in the repository.}
\label{fig:citadel_method_repo_map}
\end{figure*}
```

```latex
\begin{figure}[!t]
\centering
\includegraphics[width=\columnwidth]{figs/fig_cintas_datapath.png}
\caption{CINTAS fixed-point datapath. The selected telemetry features are normalized, transformed into linear and quadratic residual terms, aggregated over a decision block, and compared against a benign threshold.}
\label{fig:cintas_datapath}
\end{figure}
```

## Suggested Table PNGs

Use LaTeX tables for the final submission when possible. These PNG tables are useful for drafting, slides, and quick Overleaf placement checks.

```latex
\begin{figure*}[!t]
\centering
\includegraphics[width=0.95\textwidth]{figs/table_prior_slm_engines.png}
\caption{Qualitative positioning of CITADEL against prior telemetry-based SLM engines.}
\label{tab:prior_slm_engines_png}
\end{figure*}
```

```latex
\begin{figure*}[!t]
\centering
\includegraphics[width=0.95\textwidth]{figs/table_design_space_variables.png}
\caption{CITADEL design-space variables and their corresponding repository artifacts.}
\label{tab:design_space_variables_png}
\end{figure*}
```
