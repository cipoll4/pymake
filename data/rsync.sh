#!/bin/bash

SSH='adulac@tiger'

IN="/home/ama/adulac/workInProgress/networkofgraphs/process/PyNPB/data/"
OUT="./"
T="networks"

SIMUL="-n"
OPTS="--update"

if [ "$1" == "-f" ]; then
    SIMUL=""; fi

#rsync $SIMUL  -av -u --modify-window=2 --stats -m $OPTS \
rsync $SIMUL $OPTS -av --stats -m \
    -e ssh  ${SSH}:${IN}/$T/ ${OUT}/$T/

###
#rsync --dry-run  -av -u --modify-window=2  --stats --prune-empty-dirs  -e ssh --include '*/'  --include='debug/***' --exclude='*'  ./ dulac@pitmanyor:/home/dulac/ddebug
#rsync --dry-run  -av -u --modify-window=2 --stats --prune-empty-dirs  -e ssh    adulac@racer:/home/ama/adulac/workInProgress/networkofgraphs/process/PyNPB/data/networks/ ./


