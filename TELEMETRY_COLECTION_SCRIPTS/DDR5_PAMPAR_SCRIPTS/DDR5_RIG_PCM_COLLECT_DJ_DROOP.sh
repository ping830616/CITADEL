#!/bin/bash
# Author | Eduardo Ortega
folder="dj"
rm -rf $folder 
mkdir $folder
dp_pcm=1000
dp_msr=200
dp_sensor=$dp_msr
echo "*** PAMPAR DJ (DROOP) ***"
sleep 5
for i in {1..10} 
do
    echo "TRACE: $i"
    ./just_droop_ddr5.sh &
    sleep 12
    ~/PAMPAR/Apps/DJ/pthread 16 16384 ~/PAMPAR/Apps/DJ/inputDJ/1024.txt &
    sudo ~/pcm/build/bin/pcm 0.001 -i=$dp_pcm -csv="$folder/log_$i.csv" &
    ./collect_volt_data.sh $i $folder $dp_msr &
    ./collect_temp_data.sh $i $folder $dp_sensor
    sleep 40
done
