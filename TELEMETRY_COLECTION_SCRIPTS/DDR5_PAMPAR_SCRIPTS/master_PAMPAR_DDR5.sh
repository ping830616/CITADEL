#!/bin/bash
echo "DFT"
date +"%T.%3N"
./DDR5_RIG_PCM_COLLECT_DFT.sh
date+"%T.%3N"

sleep 3

echo "DJ"
date +"%T.%3N"
./DDR5_PCM_COLLECT_DJ.sh
date +"%T.%3N"

sleep 3

echo "DP"
date +"%T.%3N"
./DDR5_PCM_COLLECT_DP.sh
date +"%T.%3N"

sleep 3

echo "GL"
date +"%T.%3N"
./DDR5_PCM_COLLECT_GL.sh
date +"%T.%3N"

sleep 3

echo "GS"
date +"%T.%3N"
./DDR5_RIG_PCM_COLLECT_GS.sh
date +"%T.%3N"

sleep 3

echo "HA"
date +"%T.%3N"
./DDR5_RIG_PCM_COLLECT_HA.sh
date +"%T.%3N"

sleep 3

echo "JA"
date +"%T.%3N"
./DDR5_RIG_PCM_COLLECT_JA.sh
date +"%T.%3N"

sleep 3

echo "MM"
date +"%T.%3N"
./DDR5_RIG_PCM_COLLECT_MM.sh
date +"%T.%3N"

sleep 3

echo "NI"
date +"%T.%3N"
./DDR5_RIG_PCM_COLLECT_NI.sh
date +"%T.%3N"

sleep 3

echo "OE"
date +"%T.%3N"
./DDR5_RIG_PCM_COLLECT_OE.sh
date +"%T.%3N"

sleep 3

echo "PI"
date +"%T.%3N"
./DDR5_RIG_PCM_COLLECT_PI.sh
date +"%T.%3N"

sleep 3

echo "SH"
date +"%T.%3N"
./DDR5_RIG_PCM_COLLECT_SH.sh
date +"%T.%3N"

sleep 3

echo "TR"
date +"%T.%3N"
./DDR5_RIG_PCM_COLLECT_TR.sh
date +"%T.%3N"

sleep 3

