#!/bin/bash
# Author | Eduardo Ortega
folder="gl"
rm -rf $folder 
mkdir $folder
dp_pcm=1000
dp_msr=200
dp_sensor=$dp_msr
echo "*** PAMPAR GL (DROOP) ***"
sleep 5
for i in {1..10} 
do
    echo "TRACE: $i"
    ./just_droop_ddr4.sh &
    sleep 8
    ./GL_bchmark.sh &
    sudo ~/pcm/build/bin/pcm 0.001 -i=$dp_pcm -csv="$folder/log_$i.csv" &
    ./collect_volt_data.sh $i $folder $dp_msr &
    ./collect_temp_data.sh $i $folder $dp_sensor
    sleep 40
done
