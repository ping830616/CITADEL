#!/bin/bash
# Author | Eduardo Ortega
folder="tr"
rm -rf $folder 
mkdir $folder
dp_pcm=1000
dp_msr=200
dp_sensor=$dp_msr
echo "***PAMPAR TR***"
sleep 5
for i in {1..10} 
do
    echo "STARTING TRACE $i"
    sleep 10
    ~/PAMPAR/Apps/TR/pthread 4 2500 &
    sudo ~/pcm/build/bin/pcm 0.001 -i=$dp_pcm -csv="$folder/log_$i.csv" &
    ./collect_volt_data.sh $i $folder $dp_msr &
    ./collect_temp_data.sh $i $folder $dp_sensor
    sleep 30
done
