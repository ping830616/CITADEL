# Vivado batch synthesis for the CITADEL CINTAS streaming RTL.
#
# Usage:
#   vivado -mode batch -source scripts/vivado_cintas_synth.tcl \
#     -tclargs <tag> <part> <features> <q> <samples_per_block> <clock_period_ns>
#
# Example:
#   vivado -mode batch -source scripts/vivado_cintas_synth.tcl \
#     -tclargs A_DROOP xc7a200tfbg676-1 15 15 1000 25.000

set tag [lindex $argv 0]
set part [lindex $argv 1]
set features [lindex $argv 2]
set q [lindex $argv 3]
set samples_per_block [lindex $argv 4]
set clock_period_ns [lindex $argv 5]

if {$tag eq ""} {
    set tag "cintas"
}
if {$part eq ""} {
    set part "xc7a200tfbg676-1"
}
if {$features eq ""} {
    set features 15
}
if {$q eq ""} {
    set q 15
}
if {$samples_per_block eq ""} {
    set samples_per_block 1000
}
if {$clock_period_ns eq ""} {
    set clock_period_ns 10.000
}

set outdir "results/notebook_run/rtl_sweep/$tag"
file mkdir $outdir

set cfg [open "$outdir/run_config.csv" "w"]
puts $cfg "tag,part,features,q,samples_per_block,clock_period_ns"
puts $cfg "$tag,$part,$features,$q,$samples_per_block,$clock_period_ns"
close $cfg

read_verilog -sv rtl/cintas/cintas_stream.sv

synth_design \
    -top cintas_stream \
    -part $part \
    -generic "FEATURES=$features" \
    -generic "Q=$q" \
    -generic "SAMPLES_PER_BLOCK=$samples_per_block"

create_clock -name clk -period $clock_period_ns [get_ports clk]

report_utilization -file "$outdir/utilization.rpt"
report_timing_summary -file "$outdir/timing_summary.rpt"
report_power -file "$outdir/power.rpt"
write_checkpoint -force "$outdir/post_synth.dcp"

exit
