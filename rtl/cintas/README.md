# CINTAS RTL

`cintas_stream.sv` is a starter streaming implementation for the TCAD hardware workstream. It is not yet a completed tapeout-quality block; it exists to make the RTL/FPGA extension concrete and versioned from day one.

Next steps:

1. export Python golden vectors from `FixedPointCINTAS`
2. add a SystemVerilog testbench that streams one selected feature per cycle
3. run bit-exact simulation against the golden vectors
4. synthesize across feature budgets and Q formats
5. commit resource, latency, and energy summaries under `results/notebook_run/rtl_sweep/`
